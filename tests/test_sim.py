import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pyworld.sim import DRONE_COST, EXAMPLE, OBJECTIVES, World  # noqa: E402

SCANNER = EXAMPLE.replace("drone.move_toward(4, 3)", """found = drone.scan()
        if found:
            drone.move_toward(found[0][0], found[0][1])""")


def test_example_script_mines_ore():
    w = World(seed=1)
    assert w.deploy(EXAMPLE)
    w.run(120)
    assert w.ore > 0
    assert not [l for l in w.logs if "exceeded" in l or "Error" in l]


def test_deterministic():
    a, b = World(seed=7), World(seed=7)
    a.deploy(EXAMPLE)
    b.deploy(EXAMPLE)
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
    w.deploy(EXAMPLE)
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
    w.deploy(EXAMPLE)
    w.run(60)
    w.ore = 30
    w.unlock("cpu")
    w2 = World.load(w.save())
    assert w2.snapshot() == w.snapshot()
    w.run(20)
    w2.run(20)
    assert w2.snapshot() == w.snapshot()


def test_print_goes_to_game_log_not_stdout(capsys):
    w = World(seed=1)
    assert w.deploy("print('hello', 42)\ndef tick(drone):\n    pass\n")
    assert any("print: hello 42" in l for l in w.logs)
    assert capsys.readouterr().out == ""


def test_errors_report_player_line_and_hint():
    w = World(seed=1)
    assert not w.deploy("def tick(drone):\n    pass\nif True\n    pass\n")
    assert w.last_error["kind"] == "SyntaxError" and w.last_error["line"] == 3
    assert w.deploy("def tick(drone):\n    x = 1\n    drone.fly()\n")
    w.run(1)
    e = w.snapshot()["error"]
    assert e["kind"] == "AttributeError" and e["line"] == 3 and "the drone" in e["message"]
    w.deploy("def tick(drone):\n    n = 0\n    while True:\n        n += 1\n")
    w.run(1)
    assert w.last_error["kind"] == "BudgetExceeded" and w.last_error["line"] in (3, 4)


def test_direction_helpers_and_walls():
    w = World(seed=1)
    w.walls = {(1, 0)}
    w.deploy("def tick(drone):\n    drone.memory['r'] = [drone.right(), drone.down()]\n")
    w.run(1)
    assert w.drones[0].memory["r"] == [False, True]  # rock blocks, then one action
    assert (w.drones[0].x, w.drones[0].y) == (0, 1)


def test_new_world_starts_with_empty_tick():
    w = World(seed=1)
    w.run(5)
    assert w.tick_n == 5 and w.mined_total == 0 and w.last_error is None
    assert (w.drones[0].x, w.drones[0].y) == (0, 0)


def _solve(w, code, ticks):
    assert w.deploy(code), w.logs[-1]
    w.run(ticks)


def test_objectives_walkthrough_using_the_code_they_teach():
    w = World(seed=1)
    _solve(w, "def tick(drone):\n    drone.right()\n", 3)
    assert w.done == ["wake"]
    _solve(w, "def tick(drone):\n    drone.move_toward(4, 3)\n", 10)
    assert "travel" in w.done
    _solve(w, "def tick(drone):\n    if drone.ore_here() > 0:\n        drone.mine()\n"
              "    else:\n        drone.move_toward(4, 3)\n", 5)
    assert "mine" in w.done
    _solve(w, EXAMPLE, 200)
    assert w.done[:5] == ["wake", "travel", "mine", "deliver", "supply"]
    assert w.current_objective()["id"] == "second"
    assert w.buy_drone() and w.done[-1] == "second" and w.stats["code_buys"] == 0
    assert w.current_objective()["id"] == "scan"
    w.ore = max(w.ore, 15)
    assert w.unlock("scan")
    _solve(w, SCANNER, 2)
    assert w.done[-1] == "scan"
    _solve(w, SCANNER + "\ndef colony_tick(colony):\n    if colony.ore >= 10:\n        colony.buy_drone()\n", 100)
    assert "autobuy" in w.done and w.stats["code_buys"] >= 1
    _solve(w, SCANNER.replace("def tick(drone):", "def tick(drone):\n    drone.memory['seen'] = True"), 1)
    assert "memory" in w.done
    _solve(w, SCANNER + "\ndef colony_tick(colony):\n    if colony.ore >= 10:\n        colony.buy_drone()\n", 1500)
    assert "fleet" in w.done, (w.mined_total, len(w.drones), w.best_rate)


def test_objectives_complete_in_order_and_pay_rewards():
    w = World(seed=1)
    _solve(w, EXAMPLE, 60)  # moves, mines and delivers before 'wake' was "taught"
    assert w.done[:4] == ["wake", "travel", "mine", "deliver"]
    rewards = sum(o["reward"] for o in OBJECTIVES if o["id"] in w.done)
    assert rewards > 0 and w.ore == w.mined_total + rewards


def test_score_is_ore_delivered_in_window_and_best_is_kept():
    w = World(seed=1)
    w.tech.add("scan")
    _solve(w, SCANNER, 300)
    assert w.rate() == sum(n for t, n in w.history)
    assert all(t > w.tick_n - 100 for t, _ in w.history)
    assert w.best_rate >= w.rate() > 0
    w.deploy("def tick(drone):\n    pass\n")
    w.run(150)
    assert w.rate() == 0 and w.best_rate > 0


def test_objective_progress_survives_save_load():
    w = World(seed=1)
    _solve(w, EXAMPLE, 300)
    w2 = World.load(w.save())
    assert w2.done == w.done and w2.best_rate == w.best_rate and w2.stats == w.stats
    w.run(50)
    w2.run(50)
    assert w2.snapshot() == w.snapshot()


def test_old_saves_without_objectives_still_load():
    import json
    w = World(seed=1)
    d = w.to_dict()
    for k in ("stats", "done", "history", "best_rate"):
        d.pop(k)
    w2 = World.load(json.dumps(d))
    assert w2.done == [] and w2.best_rate == 0


def test_every_objective_has_text_and_unique_id():
    ids = [o["id"] for o in OBJECTIVES]
    assert len(ids) == len(set(ids))
    assert all(o["text"] and o["title"] and o["hint"] for o in OBJECTIVES)
