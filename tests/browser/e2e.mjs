import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";
// Usage: npm install playwright-core; node tests/browser/e2e.mjs [screenshot-dir]
// Opens dist/index.html from file:// in Chromium and plays through the main flows.
const FILE = new URL("../../dist/index.html", import.meta.url).href;
const SHOTS = process.argv[2] || "shots";
mkdirSync(SHOTS, { recursive: true });
const CHROMIUM = process.env.CHROMIUM || "/opt/pw-browsers/chromium";
const b = await chromium.launch({ executablePath: CHROMIUM, args: ["--no-sandbox"] });
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
const p = await ctx.newPage();
const net = [], errs = [];
p.on("request", r => { const u = r.url(); if (!/^(file|blob|data):/.test(u)) net.push(u); });
p.on("console", m => { if (m.type() === "error" || m.type() === "warning") errs.push(m.text()); });
p.on("pageerror", e => errs.push("pageerror: " + e.message));
const t0 = Date.now();
await p.goto(FILE);
await p.waitForSelector("#boot", { state: "detached", timeout: 90000 });
console.log("boot ms", Date.now() - t0);
await p.waitForTimeout(500);
await p.screenshot({ path: SHOTS + "/1-start.png" });
const state = () => p.evaluate(() => ({ tick: snap.tick, ore: snap.ore, done: snap.objectives.filter(o => o.done).map(o => o.id), err: snap.error, drones: snap.drones.length, code: deployedCode }));
const setCode = c => p.evaluate(c => cm.setValue(c), c);

// objective 1 via Run (auto-deploy)
await setCode("def tick(drone):\n    drone.right()\n");
await p.click("#run");
await p.waitForFunction(() => snap.objectives[0].done, null, { timeout: 15000 });
console.log("obj1", await state());
await p.waitForTimeout(400);
await p.screenshot({ path: SHOTS + "/2-obj1.png" });

// full miner at speed
await setCode(`def tick(drone):
    if drone.cargo >= drone.capacity:
        if drone.at_base():
            drone.deposit()
        else:
            drone.move_toward(0, 0)
    elif drone.ore_here() > 0:
        drone.mine()
    else:
        drone.move_toward(4, 3)
`);
await p.keyboard.press("Control+Enter").catch(() => {});
await p.evaluate(() => deploy());
await p.click('#speed button[data-tps="40"]');
await p.waitForFunction(() => snap.mined_total >= 20, null, { timeout: 60000 });
await p.click(".shop-item button");
await p.waitForTimeout(1200);
console.log("miner", await state());
await p.screenshot({ path: SHOTS + "/3-mining.png" });
await p.click("#run"); // pause

// syntax error
await setCode("def tick(drone):\n    if drone.cargo > 0\n        drone.deposit()\n");
await p.click("#deploy");
await p.waitForSelector("#errorBox:not([hidden])");
console.log("errorbox:", (await p.textContent("#errorBox")).replace(/\s+/g, " "));
await p.screenshot({ path: SHOTS + "/4-error.png" });

// runtime error with line
await setCode("def tick(drone):\n    x = 1\n    drone.fly()\n");
await p.click("#deploy");
await p.click("#step");
await p.waitForTimeout(800);
console.log("runtime err:", (await p.textContent("#errorBox")).replace(/\s+/g, " "));

// runaway: single C-level line the line budget can't catch
const good = "def tick(drone):\n    drone.move_toward(4, 3)\n";
await setCode(good); await p.click("#deploy");
await setCode("def tick(drone):\n    total = sum(range(10**10))\n");
await p.click("#deploy");
const tr = Date.now();
await p.click("#run");
await p.waitForSelector("#runawayOk:not([hidden])", { timeout: 30000 });
console.log("runaway recovered in ms", Date.now() - tr, "|", (await p.textContent("#runaway .modal")).replace(/\s+/g, " ").slice(0, 400));
await p.screenshot({ path: SHOTS + "/5-runaway.png" });
await p.click("#runawayOk");
console.log("after runaway", await state(), "editor kept:", (await p.evaluate(() => cm.getValue())).includes("10**10"));
await p.click("#step"); await p.waitForTimeout(300);
console.log("still ticking", (await state()).tick);

// runaway at deploy time (top-level)
await setCode("x = sum(range(10**10))\ndef tick(drone):\n    pass\n");
await p.click("#deploy");
await p.waitForSelector("#runawayOk:not([hidden])", { timeout: 30000 });
await p.click("#runawayOk");
console.log("deploy-runaway, code kept:", (await state()).code === good);

// reload persistence
const before = await state();
await p.reload();
await p.waitForSelector("#boot", { state: "detached", timeout: 90000 });
const after = await state();
console.log("reload persisted:", before.tick <= after.tick, before.done.length === after.done.length, after);

// docs + menu screenshots
await p.click("#docsBtn"); await p.waitForTimeout(200); await p.screenshot({ path: SHOTS + "/6-docs.png" }); await p.keyboard.press("Escape");

// phone layout
const m = await b.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
await m.goto(FILE);
await m.waitForSelector("#boot", { state: "detached", timeout: 90000 });
await m.waitForTimeout(500);
console.log("mobile horizontal overflow:", await m.evaluate(() => document.documentElement.scrollWidth > window.innerWidth));
await m.screenshot({ path: SHOTS + "/7-phone.png", fullPage: true });
const tablet = await b.newPage({ viewport: { width: 1100, height: 800 } });
await tablet.goto(FILE); await tablet.waitForSelector("#boot", { state: "detached", timeout: 90000 }); await tablet.waitForTimeout(400);
await tablet.screenshot({ path: SHOTS + "/8-1100.png" });
console.log("network:", net, "\nconsole errors:", errs);
await b.close();
