"""Pyworld sim core: a small deterministic colony world driven by player Python.

Pure Python with no third-party dependencies, so it runs both under CPython
(tests) and inside Pyodide (browser client).
"""
import builtins
import json
import math
import random
import sys

PLAYER_FILE = "<player>"
DRONE_COST = 10
MAX_DRONES = 8
CAPACITY = 5
BASE = (0, 0)
BASE_BUDGET = 200  # traced lines of player code per drone per tick
TECH = {
    "scan": {"cost": 15, "desc": "Unlock drone.scan(): find ore within 6 tiles"},
    "cpu": {"cost": 25, "desc": "+200 CPU budget per drone per tick"},
}

STARTER = '''\
# Runs once per drone, every tick. One action per tick (move / mine / deposit).
def tick(drone):
    if drone.cargo >= drone.capacity:
        if drone.at_base():
            drone.deposit()
        else:
            drone.move_toward(0, 0)      # head home
    elif drone.ore_here() > 0:
        drone.mine()
    else:
        # You have no scanner yet. The first ore patch is near (4, 3).
        drone.move_toward(4, 3)
'''

_SAFE_NAMES = (
    "abs all any bool dict divmod enumerate filter float int isinstance len list "
    "map max min pow print range reversed round set sorted str sum tuple zip "
    "True False None Exception ValueError KeyError IndexError TypeError"
).split()


class LockedError(Exception):
    """Raised when player code calls an API that has not been unlocked."""


class BudgetExceeded(BaseException):
    """Player code used up its CPU budget. BaseException so `except Exception` can't hide it."""


def _safe_import(name, *args, **kwargs):
    if name == "math":
        return math
    raise ImportError("only 'math' can be imported")


def _safe_builtins():
    b = {n: getattr(builtins, n) for n in _SAFE_NAMES}
    b["__import__"] = _safe_import
    return b


class Drone:
    def __init__(self, id, x, y):
        self.id = id
        self.x = x
        self.y = y
        self.cargo = 0
        self.memory = {}
        self.acted = False


class DroneAPI:
    """What player code sees. Internals are not reachable from here."""

    __slots__ = ("_d", "_w")

    def __init__(self, drone, world):
        self._d = drone
        self._w = world

    @property
    def id(self):
        return self._d.id

    @property
    def x(self):
        return self._d.x

    @property
    def y(self):
        return self._d.y

    @property
    def cargo(self):
        return self._d.cargo

    @property
    def capacity(self):
        return CAPACITY

    @property
    def memory(self):
        return self._d.memory

    def at_base(self):
        return (self._d.x, self._d.y) == BASE

    def ore_here(self):
        return self._w.ore_map.get((self._d.x, self._d.y), 0)

    def _act(self):
        if self._d.acted:
            return False
        self._d.acted = True
        return True

    def move(self, dx, dy):
        """Step one tile. Only the sign of dx/dy is used; diagonals are not allowed."""
        d = self._d
        if d.acted:
            return False
        sx = (dx > 0) - (dx < 0)
        sy = (dy > 0) - (dy < 0)
        if sx and sy:
            sy = 0
        nx, ny = d.x + sx, d.y + sy
        if (sx or sy) and 0 <= nx < self._w.w and 0 <= ny < self._w.h:
            d.acted = True
            d.x, d.y = nx, ny
            return True
        return False

    def move_toward(self, x, y):
        dx, dy = x - self._d.x, y - self._d.y
        if dx == 0 and dy == 0:
            return False
        if abs(dx) >= abs(dy):
            return self.move(dx, 0)
        return self.move(0, dy)

    def mine(self):
        d, w = self._d, self._w
        pos = (d.x, d.y)
        if d.acted or d.cargo >= CAPACITY or w.ore_map.get(pos, 0) <= 0:
            return False
        d.acted = True
        w.ore_map[pos] -= 1
        d.cargo += 1
        return True

    def deposit(self):
        d, w = self._d, self._w
        if d.acted or d.cargo <= 0 or (d.x, d.y) != BASE:
            return 0
        d.acted = True
        n, d.cargo = d.cargo, 0
        w.ore += n
        w.mined_total += n
        return n

    def scan(self):
        if "scan" not in self._w.tech:
            raise LockedError("drone.scan() is locked. Unlock 'scan' (15 ore).")
        d = self._d
        found = []
        for (x, y), amt in self._w.ore_map.items():
            dist = abs(x - d.x) + abs(y - d.y)
            if amt > 0 and dist <= 6:
                found.append((dist, x, y, amt))
        found.sort()
        return [(x, y, amt) for _, x, y, amt in found]


class ColonyAPI:
    __slots__ = ("_w",)

    def __init__(self, world):
        self._w = world

    @property
    def ore(self):
        return self._w.ore

    @property
    def tick(self):
        return self._w.tick_n

    @property
    def drones(self):
        return len(self._w.drones)

    @property
    def memory(self):
        return self._w.shared

    def has(self, tech):
        return tech in self._w.tech

    def buy_drone(self):
        return self._w.buy_drone()


class World:
    def __init__(self, seed=1, w=24, h=16):
        self.seed = seed
        self.w = w
        self.h = h
        self.tick_n = 0
        self.ore = 0
        self.mined_total = 0
        self.tech = set()
        self.budget = BASE_BUDGET
        self.ore_map = {}
        self.max_ore = {}
        self.drones = []
        self.next_id = 1
        self.shared = {}
        self.logs = []
        self.code = STARTER
        self._tick_fn = None
        self._colony_fn = None
        self._gen()
        self._spawn()
        self.deploy(STARTER)

    # ---- world setup -------------------------------------------------
    def _gen(self):
        rng = random.Random(self.seed)
        centers = [(4, 3)]
        for _ in range(5):
            centers.append((rng.randint(8, self.w - 3), rng.randint(2, self.h - 3)))
        for cx, cy in centers:
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    x, y = cx + dx, cy + dy
                    if dx * dx + dy * dy <= 5 and 0 <= x < self.w and 0 <= y < self.h and (x, y) != BASE:
                        if (x, y) not in self.max_ore:
                            self.max_ore[(x, y)] = rng.randint(8, 15)
        self.ore_map = dict(self.max_ore)

    def _spawn(self):
        d = Drone(self.next_id, *BASE)
        self.next_id += 1
        self.drones.append(d)
        return d

    # ---- player actions ----------------------------------------------
    def log(self, msg):
        self.logs.append("[%d] %s" % (self.tick_n, msg))
        del self.logs[:-60]

    def buy_drone(self):
        if self.ore >= DRONE_COST and len(self.drones) < MAX_DRONES:
            self.ore -= DRONE_COST
            self._spawn()
            return True
        return False

    def unlock(self, name):
        info = TECH.get(name)
        if info is None or name in self.tech or self.ore < info["cost"]:
            return False
        self.ore -= info["cost"]
        self.tech.add(name)
        if name == "cpu":
            self.budget += 200
        self.log("Unlocked %s" % name)
        return True

    def deploy(self, code):
        """Compile and load player code. On failure the old code keeps running."""
        ns = {"__builtins__": _safe_builtins(), "colony": ColonyAPI(self), "math": math}
        try:
            self._run(lambda: exec(compile(code, PLAYER_FILE, "exec"), ns))
        except BudgetExceeded:
            self.log("Deploy failed: top-level code exceeded CPU budget")
            return False
        except BaseException as e:  # SyntaxError etc.
            self.log("Deploy failed: %s: %s" % (type(e).__name__, e))
            return False
        if not callable(ns.get("tick")):
            self.log("Deploy failed: define `def tick(drone):`")
            return False
        self.code = code
        self._tick_fn = ns["tick"]
        self._colony_fn = ns.get("colony_tick")
        self.log("Code deployed")
        return True

    # ---- simulation --------------------------------------------------
    def _run(self, fn, *args):
        """Run player code, counting executed player lines against the budget."""
        budget = self.budget
        count = 0

        def local_tracer(frame, event, arg):
            nonlocal count
            if event == "line":
                count += 1
                if count > budget:
                    raise BudgetExceeded()
            return local_tracer

        def tracer(frame, event, arg):
            if event == "call" and frame.f_code.co_filename == PLAYER_FILE:
                return local_tracer
            return None

        old = sys.gettrace()
        sys.settrace(tracer)
        try:
            return fn(*args)
        finally:
            sys.settrace(old)

    def step(self):
        if self._colony_fn:
            self._guarded(self._colony_fn, ColonyAPI(self), who="colony_tick")
        for d in self.drones:
            d.acted = False
            self._guarded(self._tick_fn, DroneAPI(d, self), who="drone %d" % d.id)
        self.tick_n += 1
        if self.tick_n % 50 == 0:  # slow regrowth keeps the idle loop alive
            for pos, mx in self.max_ore.items():
                if self.ore_map[pos] < mx:
                    self.ore_map[pos] += 1

    def _guarded(self, fn, arg, who):
        try:
            self._run(fn, arg)
        except BudgetExceeded:
            self.log("%s: CPU budget exceeded (%d lines)" % (who, self.budget))
        except LockedError as e:
            self.log("%s: %s" % (who, e))
        except Exception as e:
            self.log("%s: %s: %s" % (who, type(e).__name__, e))

    def run(self, n):
        for _ in range(n):
            self.step()

    # ---- persistence / UI --------------------------------------------
    def snapshot(self):
        return {
            "w": self.w, "h": self.h, "tick": self.tick_n, "ore": self.ore,
            "mined_total": self.mined_total, "budget": self.budget,
            "tech": sorted(self.tech),
            "tech_info": {k: dict(v, owned=k in self.tech) for k, v in TECH.items()},
            "drone_cost": DRONE_COST, "max_drones": MAX_DRONES,
            "ore_tiles": [[x, y, a] for (x, y), a in self.ore_map.items() if a > 0],
            "drones": [{"id": d.id, "x": d.x, "y": d.y, "cargo": d.cargo} for d in self.drones],
            "logs": self.logs[-30:],
        }

    def to_dict(self):
        return {
            "seed": self.seed, "tick": self.tick_n, "ore": self.ore,
            "mined_total": self.mined_total, "tech": sorted(self.tech),
            "budget": self.budget, "next_id": self.next_id, "code": self.code,
            "ore_map": [[x, y, a] for (x, y), a in self.ore_map.items()],
            "drones": [
                {"id": d.id, "x": d.x, "y": d.y, "cargo": d.cargo, "memory": d.memory}
                for d in self.drones
            ],
            "shared": self.shared, "logs": self.logs,
        }

    def save(self):
        return json.dumps(self.to_dict(), default=repr)

    @classmethod
    def load(cls, text):
        s = json.loads(text)
        w = cls(seed=s["seed"])
        w.tick_n, w.ore, w.mined_total = s["tick"], s["ore"], s["mined_total"]
        w.tech, w.budget, w.next_id = set(s["tech"]), s["budget"], s["next_id"]
        w.ore_map = {(x, y): a for x, y, a in s["ore_map"]}
        w.shared = s["shared"]
        logs = list(s["logs"])
        w.drones = []
        for ds in s["drones"]:
            d = Drone(ds["id"], ds["x"], ds["y"])
            d.cargo, d.memory = ds["cargo"], ds["memory"]
            w.drones.append(d)
        if not w.deploy(s["code"]):
            w.deploy(STARTER)
        w.logs = logs
        return w
