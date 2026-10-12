// Runs Pyodide and the sim off the main thread, so the page never freezes and a
// runaway script can be stopped by terminating this worker (see Engine in the page).
// Pyodide's files arrive as Blobs from the page; fetch() and importScripts() are
// patched to serve them, so nothing touches the network and file:// works.
"use strict";
const VIRTUAL = "https://pyodide.invalid/";
const MIME = { wasm: "application/wasm", json: "application/json", zip: "application/zip", js: "text/javascript" };
let files = {}, urls = {}, py = null, api = null;

const baseName = u => String(u).split("?")[0].split("/").pop();
const realImport = self.importScripts.bind(self);
self.importScripts = (...list) => realImport(...list.map(u => {
  const n = baseName(u);
  if (!files[n]) return u;
  return (urls[n] ||= URL.createObjectURL(new Blob([files[n]], { type: "text/javascript" })));
}));
const realFetch = self.fetch.bind(self);
self.fetch = (u, opts) => {
  const n = baseName(u instanceof Request ? u.url : u);
  if (files[n]) return Promise.resolve(new Response(files[n], { headers: { "Content-Type": MIME[n.split(".").pop()] } }));
  return realFetch(u, opts);
};

const API = `
import json
from pyworld import sim

world = sim.World(seed=1)

def api(cmd, args):
    global world
    a = json.loads(args)
    out = {}
    if cmd == "new":
        world = sim.World(seed=1)
    elif cmd == "load":
        world = sim.World.load(a["save"])
    elif cmd == "run":
        world.run(a["n"])
    elif cmd == "deploy":
        out["ok"] = world.deploy(a["code"])
    elif cmd == "buy":
        out["ok"] = world.buy_drone()
    elif cmd == "unlock":
        out["ok"] = world.unlock(a["name"])
    out["snap"] = world.snapshot()
    out["save"] = world.save()
    out["code"] = world.code
    out["starter"] = sim.STARTER
    return json.dumps(out, default=repr)
`;

self.onmessage = async ({ data }) => {
  const { id, cmd, args } = data;
  try {
    let result;
    if (cmd === "init") {
      for (const [name, blob] of Object.entries(args.files)) files[name] = await blob.arrayBuffer();
      self.importScripts(VIRTUAL + "pyodide.js");
      py = await loadPyodide({ indexURL: VIRTUAL });
      py.FS.mkdirTree("/home/pyodide/pyworld");
      for (const [name, src] of Object.entries(args.sources)) py.FS.writeFile("/home/pyodide/pyworld/" + name, src);
      py.runPython(API);
      api = py.globals.get("api");
      result = true;
    } else {
      result = JSON.parse(api(cmd, JSON.stringify(args || {})));
    }
    self.postMessage({ id, ok: true, result });
  } catch (e) {
    self.postMessage({ id, ok: false, error: String(e && e.message || e) });
  }
};
