"""Build dist/index.html: one self-contained file that works offline from file://.

Inlines:
  - pyworld/*.py (the sim), run by Pyodide inside a Web Worker
  - web/worker.js (the worker that hosts Pyodide)
  - Pyodide (Python runtime) and CodeMirror 5 (editor), fetched once from the npm
    registry at pinned versions into .cache/ (git-ignored) and base64-embedded
"""
import base64
import hashlib
import io
import json
import pathlib
import tarfile
import urllib.request

root = pathlib.Path(__file__).parent
cache = root / ".cache"

PACKAGES = {
    # name: (version, sha256 of the registry tarball)
    "pyodide": ("0.26.4", "04c2d423c77ec87025d2a61e7d82fe00355a8f24471d60e012da5b3731e32ea5"),
    "codemirror": ("5.65.18", "775b7a711166c3f39899e56179a7fc8b5b755c3a043ee973c54ae5838023400f"),
}
PYODIDE_FILES = ["pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"]
CM_JS = ["lib/codemirror.js", "mode/python/python.js", "addon/edit/matchbrackets.js",
         "addon/selection/active-line.js", "addon/runmode/runmode.js"]
CM_CSS = ["lib/codemirror.css"]


def package(name):
    """Return {path inside package: bytes}, downloading the tarball on first use."""
    version, sha = PACKAGES[name]
    tgz = cache / ("%s-%s.tgz" % (name, version))
    if not tgz.exists():
        url = "https://registry.npmjs.org/%s/-/%s-%s.tgz" % (name, name, version)
        print("downloading", url)
        cache.mkdir(exist_ok=True)
        tgz.write_bytes(urllib.request.urlopen(url).read())
    data = tgz.read_bytes()
    if sha and hashlib.sha256(data).hexdigest() != sha:
        raise SystemExit("checksum mismatch for %s; delete %s and retry" % (name, tgz))
    out = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        for m in tf.getmembers():
            if m.isfile():
                out[m.name.split("/", 1)[1]] = tf.extractfile(m).read()
    return out


def script_json(obj):
    # "</" would end the surrounding <script> block early.
    return json.dumps(obj).replace("</", "<\\/")


def main():
    pyo, cm = package("pyodide"), package("codemirror")
    sources = {p.name: p.read_text() for p in sorted((root / "pyworld").glob("*.py"))}
    assets = "\n".join(
        '<script type="application/octet-stream" data-asset="%s">%s</script>'
        % (n, base64.b64encode(pyo[n]).decode()) for n in PYODIDE_FILES)
    parts = {
        "__PY_SOURCES_JSON__": script_json(sources),
        "__WORKER_JS__": (root / "web" / "worker.js").read_text().replace("</", "<\\/"),
        "__CM_JS__": "\n".join(cm[f].decode() for f in CM_JS).replace("</script", "<\\/script"),
        "__CM_CSS__": "\n".join(cm[f].decode() for f in CM_CSS),
        "__PYODIDE_ASSETS__": assets,
    }
    html = (root / "web" / "index.template.html").read_text()
    for k, v in parts.items():
        assert k in html, k
        html = html.replace(k, v)
    out = root / "dist"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html)
    print("wrote %s (%.1f MB)" % (out / "index.html", len(html) / 1e6))


if __name__ == "__main__":
    main()
