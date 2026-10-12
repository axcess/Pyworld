import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyworld.sim import DRONE_COST, World  # noqa: E402


def test_starter_script_mines_ore():
    w = World(seed=1)
    w.run(120)
    assert w.ore > 0
    assert not [l for l in w.logs if "exceeded" in l or "Error" in l]


def test_deterministic():
    a, b = World(seed=7), World(seed=7)
    a.run(80)
    b.run(80)
    assert a.snapshot() == b.snapshot()


def test_infinite_loop_hits_budget_and_world_survives():
    w = World(seed=1)
    assert w.deploy("def tick(drone):\n    while True:\n        pass\n")
    w.run(3)
    assert any("CPU budget exceeded" in l for l in w.logs)
    assert w.tick_n == 3


def test_except_exception_cannot_swallow_budget():
    w = World(seed=1)
    w.deploy("def tick(drone):\n    try:\n        while True:\n            pass\n    except Exception:\n        pass\n")
    w.run(1)
    assert any("CPU budget exceeded" in l for l in w.logs)


def test_scan_locked_until_unlocked():
    w = World(seed=1)
    w.deploy("def tick(drone):\n    drone.scan()\n")
    w.run(1)
    assert any("locked" in l for l in w.logs)
    w.ore = 100
    assert w.unlock("scan")
    w.deploy("def tick(drone):\n    drone.memory['n'] = len(drone.scan())\n")
    w.run(1)
    assert w.drones[0].memory["n"] > 0


def test_buy_drone_costs_ore():
    w = World(seed=1)
    assert not w.buy_drone()
    w.ore = DRONE_COST
    assert w.buy_drone() and len(w.drones) == 2 and w.ore == 0


def test_bad_deploy_keeps_old_code():
    w = World(seed=1)
    assert not w.deploy("def tick(drone) broken")
    assert not w.deploy("x = 1")
    w.run(5)  # still runs the starter script
    assert w.drones[0].x + w.drones[0].y > 0


def test_player_cannot_import_os_or_open_files():
    w = World(seed=1)
    assert not w.deploy("import os\ndef tick(drone):\n    pass\n")
    w.deploy("def tick(drone):\n    open('/etc/passwd')\n")
    w.run(1)
    assert any("NameError" in l for l in w.logs)


def test_one_action_per_tick():
    w = World(seed=1)
    w.deploy("def tick(drone):\n    drone.memory['a'] = [drone.move(1, 0), drone.move(1, 0)]\n")
    w.run(1)
    assert w.drones[0].memory["a"] == [True, False]


def test_save_load_roundtrip():
    w = World(seed=3)
    w.run(60)
    w.ore = 30
    w.unlock("cpu")
    w2 = World.load(w.save())
    assert w2.snapshot() == w.snapshot()
    w.run(20)
    w2.run(20)
    assert w2.snapshot() == w.snapshot()
