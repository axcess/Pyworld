# Pyworld: handoff

## Session 2 update (read first; older notes below still apply where not contradicted)
- **Direction confirmed by the user: Screeps-like, one persistent world, NOT a level/campaign game.** A level-based campaign was started and rejected; don't reintroduce levels. Teaching happens through an in-world **objectives checklist** (`OBJECTIVES` in `sim.py`); afterwards it's an open sandbox (Shapez-like) where the goal is a **high score** = ore delivered in the last 100 ticks (`best_rate`).
- Audience: just the user for now; students later. New worlds start with an empty `def tick(drone): pass` (`STARTER`); `EXAMPLE` is the old full miner (used by tests).
- **No threats/enemies.** Next depth the user wants: **bigger scrolling map, structures (build things), drone roles/bodies**.
- Delivery: single `dist/index.html`, **fully offline** (Pyodide 0.26.4 + CodeMirror 5.65.18 base64-inlined, ~19 MB; size is fine per the user). GitHub Pages still not wanted.
- Done this session: Web Worker + 3 s watchdog with restart/rollback to the previous code; error line numbers and hints (`describe()`), editor line highlighting; `print()` goes to the game log; `drone.right/left/up/down()`; `walls` support in the sim (no rocks generated yet); CodeMirror editor; new canvas art (vector drones in Okabe-Ito colours, crystals, base, floating +ore); responsive layout (phone order: objective, map, code); tile hover coordinates; drone inspector (memory); save export/import; objectives moved `scan` early because the first patch's centre tile runs dry and stalls the `EXAMPLE` miner.
- Verify: `python3 -m pytest tests` (20 tests) and `node tests/browser/e2e.mjs` (needs `playwright-core`; checks zero network requests from file://, objectives, errors, runaway recovery, reload, phone layout).
- Branch this session: `claude/eager-bell-bwpr3d`.

## Session 2b: curriculum + reskin (read this too)
- The user's course is **CodeHS Intro to Python, Units 1–7** (Drive folder they shared): Karel (commands, functions, top-down design, comments, for/if/else/while, parameters), print/variables/types/input/math/string ops, booleans/comparison/logical operators/floats+round, Quiz Game (score variable), while/for i in range/break/continue/nested control. **Lists, dicts, classes and return values are NOT in the course**; the user still wants a "beyond the course" tier with lists and **classes**.
- **The user rejected Karel-style APIs** ("is it really indicative of how python looks?"). Use real-Python object style (`drone.go_to(x, y)`, `drone.is_full()`), not `move()/turn_left()`.
- Agreed direction, not built yet: a **short tutorial of single commands that ends at `def loop(colony):`** (one Screeps-style entry point, `for drone in colony.drones:`), objectives labelled by course unit, a later "beyond the course" tier (lists, classes). Ideas from TooAngel/screeps (AGPL: ideas only, no code): role functions, task lists, bodies from parts, role counts, depot/hauler logistics, quests as class challenges.
- Later, not now: a shared class map hosted from the teacher's laptop on the LAN during class; students' code would run in their own browsers and send actions to the host.
- Reskin done: Kenney CC0 packs (space sprites, sci-fi UI 9-slice panels, Kenney Future font, sounds with mute) in `assets/kenney/`, inlined by `build.py` via `{{asset:path}}`. Kenney Future's lowercase x looks like H, so everything using that font is uppercased.

---

# Original handoff (session 1)

You are picking up a working prototype. Goal now: **polish it into something worth playtesting repeatedly**, without breaking the architecture below. Read this whole file, then `README.md`, then `pyworld/sim.py` (~390 lines) before changing anything.

## Product vision
An open-world, single-player, incremental/idle colony sim where **the player's Python is the only way to act** (think Screeps, but Python and single-player). Progression comes from better code plus unlocked APIs and CPU budget, not just bigger numbers. Long-term, the audience may include students (the user is considering Chromebooks, a CodeHS-like Karel-style on-ramp, and schools); do not assume that yet.

## Decisions already made with the user
- **Single-player, browser-based, Python runs in-browser via Pyodide.** No game server. (The user dismissed the interface/scope questions, then confirmed this direction by asking for a downloadable HTML to test.)
- **Delivery for now:** a single self-contained `dist/index.html`, opened locally on the user's laptop in Chrome. GitHub Pages was discussed and **declined for now**. Do not add Pages workflows unless asked.
- The user wants an MVP they can test, then iterate. They have not yet reported playtest feedback.
- Costs: keep it near $0. No backend, no accounts, no cloud saves.
- Pronouns: the user has not stated any; use they/them if you must refer to them.

## Current state (all committed and pushed on `claude/affectionate-volta-u91qg1`)
| Path | Purpose |
|---|---|
| `pyworld/sim.py` | Deterministic sim core and player-code sandbox. Pure Python, no deps; runs under CPython and Pyodide |
| `web/index.template.html` | The client (canvas map, textarea editor, shop, log, API cheat sheet). Contains the placeholder `__SIM_PY_JSON__` |
| `build.py` | Inlines `sim.py` into the template, writing `dist/index.html` (`</` is escaped so it cannot close the script tag) |
| `dist/index.html` | Built output, committed so it can be downloaded |
| `tests/test_sim.py` | 10 pytest tests, all passing |
| `README.md` | How to run and layout |

The `dist/` file must be rebuilt (`python3 build.py`) after any change to `sim.py` or the template. The user tests the built file.

### Game as implemented
- 24x16 grid, base at (0,0), six ore patches (first one fixed near (4,3); others seeded, `seed=1`). Ore tiles hold 8-15 and regrow +1 every 50 ticks.
- Player defines `def tick(drone):` (runs per drone per tick) and optionally `def colony_tick(colony):`.
- One action per drone per tick (move / mine / deposit); extra actions return False/0.
- Drone API: `x, y, cargo, capacity (5), id, memory, at_base(), ore_here(), move(dx,dy)` (no diagonals), `move_toward(x,y)`, `mine()`, `deposit()`, `scan()` (locked behind tech, radius 6 Manhattan).
- Colony API: `ore, drones, tick, memory, has(tech), buy_drone()`.
- Shop: drones cost 10 ore (max 8); tech `scan` 15, `cpu` 25 (+200 budget).
- CPU budget: traced player lines per drone per tick (200 base) via `sys.settrace`; only frames with filename `"<player>"` are counted. `BudgetExceeded` subclasses `BaseException` so `except Exception` cannot swallow it.
- Sandbox: restricted builtins whitelist (`_SAFE_NAMES`), custom `__import__` allowing only `math`. `DroneAPI`/`ColonyAPI` use `__slots__` and expose no internals.
- Persistence: `World.save()/load()` JSON, stored in `localStorage` key `pyworld-mvp-save-v1`; on load, up to 600 missed ticks (1/sec) are simulated and a toast shows ore gained. Bad deploys keep the previous code running.

## Verification already done (and how to redo it)
- `python3 -m pytest -q tests` -> 10 passed.
- Sim verified under real Pyodide 0.26.4 in Node (budget catches infinite loops; save/load works).
- Full UI verified in Chromium via Playwright, with no console errors, ore mined, locked-`scan()` error shown.
- **The sandbox's network blocks `cdn.jsdelivr.net` (403)**, so the browser test serves Pyodide locally: `npm install pyodide@0.26.4 playwright-core`, launch `chromium` with `executablePath: "/opt/pw-browsers/chromium"` and `--no-sandbox`, and `page.route("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/*", ...)` to fulfil requests from `node_modules/pyodide/`, then `goto("file:///.../dist/index.html")`. Put scratch files in the session scratchpad, not the repo.
- Not yet verified: loading from the real CDN, other browsers, an actual Chromebook, any playtest by the user.

## Known limitations / tech debt
1. **Python runs on the main thread**, so heavy scripts stall the UI slightly. Next step: move Pyodide into a Web Worker. Note Chrome blocks worker/WASM fetches from `file://` pages unless the worker is created from a Blob and assets are handled carefully; test this with the single-file `file://` flow the user relies on.
2. **Budget counts traced *lines*, not real time**; a single line like `sum(range(10**9))` can still hang. Consider a wall-clock guard (easier in a worker, which can be terminated).
3. **Sandbox is not hardened for a shared server.** Fine for local single-player; do not market it as secure multiplayer.
4. First load needs internet (Pyodide from jsdelivr). Offline/bundled Pyodide was discussed but is not done.
5. `dist/index.html` is generated but committed; avoid merge confusion by always rebuilding rather than hand-editing.
6. System notices during the session said `web/index.template.html` and `pyworld/sim.py` "changed on disk" after my edits (likely my own build/edit steps). The committed versions are the source of truth; run `git diff` before editing to confirm a clean tree.
7. Editor is a plain `<textarea>`: no syntax highlighting, no line numbers, no inline error markers.
8. Logs show errors but not tracebacks or line numbers from player code.

## Polish backlog (suggested priority)
**P0: fix what the player will hit first**
- Error UX: show line number and message for player exceptions and deploy failures; highlight in editor.
- Clearer first-run onboarding: a short guided first goal ("make the drone reach the ore", then "earn 15 ore, unlock scan"), instead of only a cheat sheet.
- Web Worker execution (see debt #1) with a visible "script running too long" recovery.

**P1: feel**
- Better visuals: drone movement interpolation, ore/depletion feedback, base sprite, color-blind-safe palette, responsive layout for small screens.
- Show per-drone CPU usage and the budget in the UI; per-drone selection, memory inspector.
- Editor upgrade (CodeMirror 6 with Python mode, pinned to a cdnjs/jsdelivr version) while keeping the single-file build working.
- Sound/haptics are optional and low priority.

**P2: depth (keep tuning separate from architecture)**
- Tech tree with more API unlocks (pathfinding helper, `colony_tick` features, radio/memory sharing).
- Production chain (ore -> refined -> new drone types), a second resource, regrowth/biomes, a larger or scrolling world.
- Light threat/event system; prestige ("Refactor") that keeps code and grants permanent upgrades.
- Challenges with replay/score (deterministic sim makes this cheap).

**P3: delivery**
- PWA/service worker or bundled Pyodide for offline use; optional GitHub Pages workflow only if the user asks.
- Export/import save file.

## Working agreements
- Develop on `claude/affectionate-volta-u91qg1`; commit with clear messages; push with `git push -u origin <branch>`. **Do not open a PR unless the user asks.**
- Commit trailer used so far: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and the `Claude-Session:` line from the session reminder (follow whatever the current reminder says).
- Keep `sim.py` dependency-free and deterministic (`random.Random(seed)` only); every new rule gets a pytest test; run tests and rebuild `dist/` before finishing.
- Keep the single-file, double-click-to-open delivery working; after changes, redeliver the built file to the user (they test locally).
- Do not weaken the sandbox (no new builtins/imports without a test proving they are safe).
- Ask the user before large scope changes (multiplayer, backend, accounts, monetization). Prefer a recommendation over a menu of options.
