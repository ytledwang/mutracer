#!/usr/bin/env python3
"""远端运行（python3.8）：把 m4-scene.json + 资产打包提交到 127.0.0.1:8787，poll 到 succeed，render.png 写 stdout 对应文件。
env: MUTRACER_API_TOKEN。argv: scene.json chess.glb glb_key view out.png"""
import base64, json, os, sys, time, urllib.request, urllib.error
scene_p, glb_p, glb_key, view, out_p = sys.argv[1:6]
ROOT = "/tmp/mutracer-fridge-assets"
API = "http://127.0.0.1:8787"
TOK = os.environ["MUTRACER_API_TOKEN"]
def req(path, payload=None, timeout=120):
    data = None if payload is None else json.dumps(payload).encode()
    r = urllib.request.Request(API + path, data=data, headers={"Authorization": "Bearer " + TOK, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as x: return x.status, x.read()
    except urllib.error.HTTPError as e:
        raise SystemExit("HTTP %s %s: %s" % (e.code, path, e.read()[:300]))
scene = json.load(open(scene_p))
models, meshes = scene["models"], scene["meshes"]
urls = set()
for m in models.values():
    if m.get("type") == "model" and m.get("is_visible") is not False and m.get("mesh"):
        u = meshes[m["mesh"]].get("url")
        if u: urls.add(u)
for t in scene.get("textures", {}).values():
    if isinstance(t, dict) and t.get("urls"): urls.add(t["urls"])
assets, missing = {}, 0
for u in sorted(urls):
    p = os.path.join(ROOT, u)
    if u == glb_key: p = glb_p
    if os.path.isfile(p): assets[u] = base64.b64encode(open(p, "rb").read()).decode()
    else: missing += 1
sys.stderr.write("assets=%d missing(non-visible/official)=%d payload~%dMB\n" % (len(assets), missing, sum(map(len, assets.values())) // 1000000))
params = {"view": view, "width": 640, "height": 360, "samples": 32, "bounces": 4, "denoise": True, "timeout_ms": 600000, "tone_mapping": "agx", "light_scale": 1}
st, body = req("/v1/jobs", {"kind": "render", "scene": scene, "assets": assets, "params": params}, 300)
job = json.loads(body)["id"]; sys.stderr.write("cloud_job_id=%s\n" % job)
t0 = time.time()
while True:
    j = json.loads(req("/v1/jobs/" + job, timeout=30)[1])
    if j["status"] == "succeed": break
    if j["status"] == "failed": raise SystemExit("job failed: %s" % j.get("error"))
    if time.time() - t0 > 600: raise SystemExit("timeout 600s")
    time.sleep(2)
open(out_p, "wb").write(req("/v1/jobs/%s/render.png" % job)[1])
sys.stderr.write("cloud_status=succeed elapsed=%.0fs\n" % (time.time() - t0))
print(job)
