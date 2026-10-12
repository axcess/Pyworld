# Pyworld

Single-player, Screeps-style colony sandbox where **your Python is the only way to act**. Drones mine ore; you write the `tick(drone)` code that drives them, then spend ore on more drones and API/CPU upgrades. An in-game objectives checklist teaches the basics (functions, `if/elif`, comparisons, lists, dictionaries) inside the live world, then leaves you in a sandbox chasing a high score: ore delivered in the last 100 ticks.

## Try it
Download `dist/index.html` and double-click it (Chrome or Edge). It is one ~19 MB file that **works offline**: the Python runtime (Pyodide) and the code editor are built in, and nothing is fetched from the network.

1. Follow the objective on the left: edit the code, **Deploy** (Ctrl+Enter), then **▶ Run**.
2. Spend ore in the Shop: more drones, `scan` (unlocks `drone.scan()`), `cpu` (bigger per-tick budget).
3. Progress saves in the browser. Coming back simulates up to 600 missed ticks. **⋯** has save export/import and reset.

## Safety rails for experimenting
- Errors show the line number, highlight it in the editor, and give a plain-English hint.
- Each drone gets a CPU budget of traced lines per tick, so `while True:` just idles that drone.
- Python runs in a Web Worker with a 3-second watchdog. Anything slower (for example `sum(range(10**10))`) gets stopped, Python restarts, the game pauses, and the drones go back to your previous working code. Your editor text is kept.

## Layout
- `pyworld/sim.py`: deterministic sim core, sandbox, objectives and score (pure Python, no dependencies)
- `web/index.template.html`: the client; `web/worker.js`: hosts Pyodide in a worker
- `build.py`: downloads pinned Pyodide and CodeMirror tarballs from npm into `.cache/` (git-ignored; sha256-checked) and inlines everything into `dist/index.html`
- `tests/`: `python3 -m pytest tests`; browser test: `npm install playwright-core && node tests/browser/e2e.mjs`

## Known limits
- The sandbox is restricted builtins plus a CPU budget and a watchdog. Fine on your own machine; not hardened for a shared server.
