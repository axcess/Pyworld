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
# The game calls tick() once per turn for every drone you own.
# Each turn a drone can do ONE action: move, mine or deposit.
# Open the Objectives panel to get started.

def tick(drone):
    pass
'''

# A complete miner. Objectives build up to this; tests use it as a known-good script.
EXAMPLE = '''\
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

RATE_WINDOW = 100  # score: ore delivered in the last RATE_WINDOW ticks


def _any_memory(w):
    return any(d.memory for d in w.drones) or bool(w.shared)


# The objectives are the tutorial: each one checks the live world, then pays a reward.
# Text uses a tiny markdown: `code`, **bold**, blank-line paragraphs and ``` blocks.
OBJECTIVES = [
    dict(
        id="wake", title="Wake up the drone", reward=0,
        check=lambda w: w.stats["moves"] >= 3,
        text="""Your drone 🤖 waits at the base 🏠 in the top-left corner. The game calls your `tick(drone)` function **once every turn**.

Replace `pass` with:

```
def tick(drone):
    drone.right()
```

Press **Deploy**, then **▶ Run**. Each turn, the drone steps one tile right.""",
        hint="Lines inside def tick(drone): must be indented by 4 spaces (press Tab).",
    ),
    dict(
        id="travel", title="Head for the ore", reward=0,
        check=lambda w: any(w.ore_map.get((d.x, d.y), 0) > 0 for d in w.drones),
        text="""Ore 💎 glitters at around **(4, 3)**. Positions are (x, y): x counts tiles to the right, y counts tiles **down**, and the base is (0, 0).

`drone.move_toward(x, y)` takes one step toward a spot:

```
def tick(drone):
    drone.move_toward(4, 3)
```""",
        hint="Use drone.move_toward(4, 3). The drone stops once it gets there.",
    ),
    dict(
        id="mine", title="Dig in", reward=0,
        check=lambda w: w.stats["mined"] >= 3,
        text="""`drone.mine()` picks up 1 ore from the tile underneath. But the drone has to **decide**: mine if there's ore here, otherwise keep walking. That's an `if`:

```
def tick(drone):
    if drone.ore_here() > 0:
        drone.mine()
    else:
        drone.move_toward(4, 3)
```

Each turn, only one branch runs.""",
        hint="drone.ore_here() is how much ore is under the drone. > means greater than.",
    ),
    dict(
        id="deliver", title="Bring it home", reward=5,
        check=lambda w: w.mined_total >= 1,
        text="""The drone holds **5** ore (`drone.capacity`). `drone.cargo` is how much it carries. When it's full it should go home and `drone.deposit()`, which only works at the base.

Check "am I full?" **first**, using `elif` to chain the choices:

```
def tick(drone):
    if drone.cargo >= drone.capacity:
        if drone.at_base():
            drone.deposit()
        else:
            drone.move_toward(0, 0)
    elif drone.ore_here() > 0:
        drone.mine()
    else:
        drone.move_toward(4, 3)
```""",
        hint="If the drone just sits on the ore when full, check the order of your if / elif.",
    ),
    dict(
        id="supply", title="Steady supply", reward=5,
        check=lambda w: w.mined_total >= 20,
        text="""Your code now runs the colony on its own. Let it run until **20 ore** has been delivered.

While you wait: **💎 Ore** is what you have to spend, and the **Score** is how much you delivered in the last 100 turns. Faster code means a higher score.""",
        hint="Raise the speed with the speed control next to Run.",
    ),
    dict(
        id="second", title="Hire a helper", reward=0,
        check=lambda w: len(w.drones) >= 2,
        text="""Spend 10 ore on a second drone in the **Shop**. The same `tick(drone)` runs for **every** drone, so your code works for both, with no changes.""",
        hint="The Buy drone button is in the Shop panel.",
    ),
    dict(
        id="scan", title="Eyes on the map", reward=10,
        check=lambda w: w.stats["scans"] >= 1,
        text="""Two drones empty the first patch fast, and a drone standing on an empty tile just waits. Unlock **scan** in the Shop (15 ore). Then `drone.scan()` returns a **list** of nearby ore, closest first:

```
found = drone.scan()      # [(x, y, amount), ...]
if found:
    x, y, amount = found[0]
    drone.move_toward(x, y)
```

An empty list counts as False, so `if found:` means "if anything was found".""",
        hint="Use scan() in the else branch, instead of always walking to (4, 3). It's OK if scan() finds nothing.",
    ),
    dict(
        id="autobuy", title="Automate the shop", reward=10,
        check=lambda w: w.stats["code_buys"] >= 1,
        text="""Let your code do the shopping. If you define `colony_tick(colony)`, the game runs it once per turn, before the drones move:

```
def colony_tick(colony):
    if colony.ore >= 10:
        colony.buy_drone()
```

`colony.ore`, `colony.drones` and `colony.tick` tell you about the colony.""",
        hint="Put colony_tick next to tick (not inside it), and Deploy again.",
    ),
    dict(
        id="memory", title="Remember things", reward=10,
        check=_any_memory,
        text="""Each drone has a `drone.memory` dictionary that survives between turns. Use it to remember a target or a job:

```
if "target" not in drone.memory:
    drone.memory["target"] = (4, 3)
x, y = drone.memory["target"]
```

Ideas: give each drone a different patch using `drone.id`, or keep a counter.""",
        hint="Store anything in drone.memory['some_name'] = value. colony.memory is shared by everyone.",
    ),
    dict(
        id="fleet", title="Fleet", reward=25,
        check=lambda w: len(w.drones) >= 5 and w.mined_total >= 150,
        text="""Grow to **5 drones** and **150 ore** delivered in total. Unlocking **cpu** in the Shop gives each drone more lines of code per turn, for smarter logic.""",
        hint="Make sure drones don't all chase the same tile: scan() results help spread them out.",
    ),
    dict(
        id="score", title="High score", reward=0,
        check=lambda w: w.best_rate >= 100,
        text="""You've learned the whole API. Now it's a sandbox: reach a **score of 100** (ore delivered in 100 turns), then keep beating your best.

Ideas: fill up at the closest patch, skip empty tiles, send each drone somewhere different, buy drones at the right moment.""",
        hint="Watch the drones: any drone that is waiting around is lost score.",
    ),
]
OBJECTIVE_IDS = [o["id"] for o in OBJECTIVES]

_SAFE_NAMES = (
    "abs all any bool dict divmod enumerate filter float int isinstance len list "
    "map max min pow print range reversed round set sorted str sum tuple zip "
    "True False None Exception ValueError KeyError IndexError TypeError"
).split()


class LockedError(Exception):
    """Raised when player code calls an API that has not been unlocked."""


class BudgetExceeded(BaseException):
    """Player code used up its CPU budget. BaseException so `except Exception` can't hide it."""

    def __init__(self, line=None):
        super().__init__(line)
        self.line = line


def player_line(exc):
    """Line number in player code where `exc` happened, or None."""
    if isinstance(exc, SyntaxError) and exc.filename == PLAYER_FILE:
        return exc.lineno
    if isinstance(exc, BudgetExceeded):
        return exc.line
    line, tb = None, exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == PLAYER_FILE:
            line = tb.tb_lineno
        tb = tb.tb_next
    return line


_HINTS = {
    "NameError": "Python doesn't know that name. Check the spelling and capital letters, "
                 "and make sure you created it before using it.",
    "IndentationError": "The spaces at the start of the lines don't line up. Code inside "
                        "if / for / while / def must be indented by the same amount (4 spaces).",
    "TabError": "Mixed tabs and spaces. Use 4 spaces for each indent.",
    "SyntaxError": "Python can't read this line. Look for a missing ':' at the end of "
                   "if / for / while / def lines, or brackets and quotes that don't match.",
    "AttributeError": "That doesn't exist. Check the spelling against the API list.",
    "TypeError": "A value of the wrong kind, or the wrong number of values in the brackets.",
    "ZeroDivisionError": "You divided by zero.",
    "IndexError": "That position is past the end of the list.",
    "KeyError": "That key isn't in the dictionary yet.",
    "LockedError": "",
    "BudgetExceeded": "Your code ran too many lines. A loop that never ends is the usual cause: "
                      "check that every `while` condition eventually becomes False.",
}


def describe(exc):
    """Beginner-friendly error report: {kind, message, line, hint}."""
    kind = type(exc).__name__
    if isinstance(exc, BudgetExceeded):
        msg = "Ran out of CPU budget"
    elif isinstance(exc, SyntaxError):
        msg = exc.msg
    else:
        msg = str(exc)
    if kind == "AttributeError" and "DroneAPI" in msg:
        msg = msg.replace("'DroneAPI' object", "the drone").replace("'LevelDroneAPI' object", "the drone")
    return {"kind": kind, "message": msg, "line": player_line(exc), "hint": _HINTS.get(kind, "")}


def _safe_import(name, *args, **kwargs):
    if name == "math":
        return math
    raise ImportError("only 'math' can be imported")


def _safe_builtins(world=None):
    b = {n: getattr(builtins, n) for n in _SAFE_NAMES}
    b["__import__"] = _safe_import
    if world is not None:
        def print(*args, sep=" ", end=""):  # noqa: A001 - shadows on purpose
            world.out(str(sep).join(str(a) for a in args) + str(end))
        b["print"] = print
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
        return (self._d.x, self._d.y) == self._w.base

    def ore_here(self):
        return self._w.ore_map.get((self._d.x, self._d.y), 0)

    def _done(self, what):
        """Record a successful action (lets campaign levels count steps)."""
        self._w.on_action(self._d, what)

    def _fail(self, why):
        self._w.on_fail(self._d, why)

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
        if not (sx or sy):
            return False
        if 0 <= nx < self._w.w and 0 <= ny < self._w.h and (nx, ny) not in self._w.walls:
            d.acted = True
            d.x, d.y = nx, ny
            self._done("move")
            return True
        self._fail("bumped into %s" % ("the edge" if (nx, ny) not in self._w.walls else "a rock"))
        return False

    def right(self):
        """Step one tile right (x + 1)."""
        return self.move(1, 0)

    def left(self):
        """Step one tile left (x - 1)."""
        return self.move(-1, 0)

    def up(self):
        """Step one tile up (y - 1)."""
        return self.move(0, -1)

    def down(self):
        """Step one tile down (y + 1)."""
        return self.move(0, 1)

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
        if d.acted:
            return False
        if d.cargo >= CAPACITY:
            self._fail("tried to mine but the cargo hold is full")
            return False
        if w.ore_map.get(pos, 0) <= 0:
            self._fail("tried to mine but there is no ore here")
            return False
        d.acted = True
        w.ore_map[pos] -= 1
        d.cargo += 1
        self._done("mine")
        return True

    def deposit(self):
        d, w = self._d, self._w
        if d.acted:
            return 0
        if (d.x, d.y) != w.base:
            self._fail("tried to deposit away from base")
            return 0
        if d.cargo <= 0:
            self._fail("tried to deposit with an empty cargo hold")
            return 0
        d.acted = True
        n, d.cargo = d.cargo, 0
        w.ore += n
        w.mined_total += n
        self._done("deposit")
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
        self._w.stats["scans"] += 1
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
        self.base = BASE
        self.walls = set()
        self.last_error = None
        self.stats = {"moves": 0, "mined": 0, "code_buys": 0, "scans": 0}
        self.done = []          # ids of completed objectives, in order
        self.history = []       # (tick, ore delivered that tick) for the score
        self.best_rate = 0
        self.in_code = False    # True while player code runs (to tell code buys from UI buys)
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

    def out(self, text):
        """Output of the player's print()."""
        self.log("print: " + text[:200])

    def on_action(self, drone, what):
        """A drone action succeeded."""
        if what == "move":
            self.stats["moves"] += 1
        elif what == "mine":
            self.stats["mined"] += 1

    def on_fail(self, drone, why):
        """A drone action was refused. Kept quiet: tick-based code retries constantly."""

    # ---- objectives / score ---------------------------------------------
    def current_objective(self):
        for o in OBJECTIVES:
            if o["id"] not in self.done:
                return o
        return None

    def check_objectives(self):
        """Complete objectives in order; several can finish at once."""
        while True:
            o = self.current_objective()
            if o is None or not o["check"](self):
                return
            self.done.append(o["id"])
            self.ore += o["reward"]
            self.log("Objective complete: %s%s" % (
                o["title"], " (+%d ore)" % o["reward"] if o["reward"] else ""))

    def rate(self):
        return sum(n for t, n in self.history if t > self.tick_n - RATE_WINDOW)

    def error(self, who, exc):
        info = describe(exc)
        info["who"] = who
        info["tick"] = self.tick_n
        self.last_error = info
        where = " (line %d)" % info["line"] if info["line"] else ""
        self.log("%s: %s: %s%s" % (who, info["kind"], info["message"], where))
        return info

    def buy_drone(self):
        if self.ore >= DRONE_COST and len(self.drones) < MAX_DRONES:
            self.ore -= DRONE_COST
            self._spawn()
            if self.in_code:
                self.stats["code_buys"] += 1
            self.check_objectives()
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
        self.check_objectives()
        return True

    def deploy(self, code):
        """Compile and load player code. On failure the old code keeps running."""
        ns = {"__builtins__": _safe_builtins(self), "colony": ColonyAPI(self), "math": math}
        try:
            self._run(lambda: exec(compile(code, PLAYER_FILE, "exec"), ns))
        except (Exception, BudgetExceeded) as e:  # SyntaxError etc.
            self.error("Deploy failed", e)
            return False
        if not callable(ns.get("tick")):
            self.last_error = {"kind": "Missing tick", "message": "define `def tick(drone):`",
                               "line": None, "hint": "", "who": "Deploy failed", "tick": self.tick_n}
            self.log("Deploy failed: define `def tick(drone):`")
            return False
        self.code = code
        self._tick_fn = ns["tick"]
        self._colony_fn = ns.get("colony_tick")
        self.last_error = None
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
                    raise BudgetExceeded(frame.f_lineno)
            return local_tracer

        def tracer(frame, event, arg):
            if event == "call" and frame.f_code.co_filename == PLAYER_FILE:
                return local_tracer
            return None

        old = sys.gettrace()
        self.in_code = True
        sys.settrace(tracer)
        try:
            return fn(*args)
        finally:
            sys.settrace(old)
            self.in_code = False

    def step(self):
        before = self.mined_total
        if self._colony_fn:
            self._guarded(self._colony_fn, ColonyAPI(self), who="colony_tick")
        for d in self.drones:
            d.acted = False
            self._guarded(self._tick_fn, DroneAPI(d, self), who="drone %d" % d.id)
        self.tick_n += 1
        if self.mined_total > before:
            self.history.append((self.tick_n, self.mined_total - before))
        self.history = [h for h in self.history if h[0] > self.tick_n - RATE_WINDOW]
        if self.tick_n >= RATE_WINDOW:  # only full windows count toward the best score
            self.best_rate = max(self.best_rate, self.rate())
        self.check_objectives()
        if self.tick_n % 50 == 0:  # slow regrowth keeps the idle loop alive
            for pos, mx in self.max_ore.items():
                if self.ore_map[pos] < mx:
                    self.ore_map[pos] += 1

    def _guarded(self, fn, arg, who):
        try:
            self._run(fn, arg)
        except BudgetExceeded as e:
            self.error(who, e)
            self.logs[-1] = "[%d] %s: CPU budget exceeded (%d lines)%s" % (
                self.tick_n, who, self.budget, " at line %d" % e.line if e.line else "")
        except LockedError as e:
            self.error(who, e)
        except Exception as e:
            self.error(who, e)

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
            "ore_tiles": [[x, y, a, self.max_ore.get((x, y), a)] for (x, y), a in self.ore_map.items()],
            "drones": [{"id": d.id, "x": d.x, "y": d.y, "cargo": d.cargo, "memory": d.memory}
                       for d in self.drones],
            "capacity": CAPACITY,
            "logs": self.logs[-30:],
            "base": list(self.base), "walls": sorted(list(p) for p in self.walls),
            "error": self.last_error,
            "score": self.rate(), "best_score": self.best_rate, "rate_window": RATE_WINDOW,
            "objectives": [
                {"id": o["id"], "title": o["title"], "text": o["text"], "hint": o["hint"],
                 "reward": o["reward"], "done": o["id"] in self.done}
                for o in OBJECTIVES
            ],
            "objective": (self.current_objective() or {}).get("id"),
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
            "stats": self.stats, "done": self.done,
            "history": [list(h) for h in self.history], "best_rate": self.best_rate,
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
        w.stats.update(s.get("stats", {}))
        w.done = [i for i in s.get("done", []) if i in OBJECTIVE_IDS]
        w.history = [tuple(h) for h in s.get("history", [])]
        w.best_rate = s.get("best_rate", 0)
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
