"""Inline pyworld/sim.py into web/index.template.html -> dist/index.html (single file)."""
import json
import pathlib

root = pathlib.Path(__file__).parent
html = (root / "web" / "index.template.html").read_text()
sim = (root / "pyworld" / "sim.py").read_text()
# "</" would terminate the <script> block early if it appeared in the source.
payload = json.dumps(sim).replace("</", "<\\/")
out = root / "dist"
out.mkdir(exist_ok=True)
(out / "index.html").write_text(html.replace("__SIM_PY_JSON__", payload))
print("wrote", out / "index.html")
