# Pyworld (MVP candidate)

Single-player incremental colony sim where your Python is the only way to act. Drones mine ore; you write the code that drives them, then spend ore on drones and API/CPU upgrades.

## Try it
Open `dist/index.html` in Chrome (double-click works, including from a downloaded folder). The first load needs internet: it fetches the Pyodide Python runtime (~10 MB) from a CDN, and the browser caches it afterwards.

1. Press **Run** and watch the starter script mine.
2. Edit the code, **Deploy** (Ctrl+Enter).
3. Spend ore: more drones, `scan` (unlocks `drone.scan()`), `cpu` (bigger per-tick budget).
4. Progress is saved in the browser. Closing the tab and returning simulates up to 600 missed ticks.

## Layout
- `pyworld/sim.py`: deterministic sim core and sandbox (pure Python, no dependencies)
- `web/index.template.html`: the client; `python3 build.py` inlines the sim into `dist/index.html`
- `tests/`: `python3 -m pytest tests`

## Known limits
- Sandbox is restricted builtins plus a traced-line CPU budget. It runs on the student's own machine in the browser, but it is not hardened for a shared server.
- Python runs on the main thread, so a budget-exhausting script slows the page slightly; moving it to a Web Worker is the next step.
