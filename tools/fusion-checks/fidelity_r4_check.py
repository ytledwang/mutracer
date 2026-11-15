#!/usr/bin/env python3
"""r4 checker: exit 0 only if the candidate render reduces the diff vs the 1.0 gold
relative to the r2 baseline (and the best previous r4 round, if given).
Exit 1 = not improved; exit 2 = integrity/security failure.
Usage: fidelity_r4_check.py CANDIDATE.png PARAMS.json OUT_METRICS.json [--best PREV_METRICS.json]"""
import hashlib, json, os, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from fidelity_r4_analyze import load, fg_mask, ssim_lum, LUM  # same metric code as the analysis

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GOLD = os.path.join(ROOT, "docs/prd/evidence/fusion/fidelity/r2/reference-fridge-ref-front-329c-1920.png")
GOLD_SHA = "21aafa96599e4f164a0efa84cd98b79eecee1153079fe94b44de75e1816fbc80"
INNER = os.path.join(ROOT, "tools/dual-track/blender/blender_inner.py")
INNER_SHA = "f767d7ef5ef25a2ec14cf40ee3a55ec081742c6078d6e778b5fb34794db05a42"
BASE = {"mae": 12.7765, "mae_fg": 34.4164, "ssim": 0.921622}  # r2, same metric code
R4 = os.path.join(ROOT, "docs/prd/evidence/fusion/fidelity/r4")
SECRET = re.compile(rb"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}|X-Amz-Signature|[?&]token=|AKIA[0-9A-Z]{16}|service_role")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def fail(code, msg, out=None, rep=None):
    print(("FAIL" if code == 2 else "NOT_IMPROVED") + ": " + msg)
    if out and rep is not None:
        rep["status"] = "FAIL" if code == 2 else "NOT_IMPROVED"; rep["reason"] = msg
        json.dump(rep, open(out, "w"), indent=1)
    sys.exit(code)


def main():
    a = sys.argv[1:]
    best = None
    global INNER_SHA, R4
    if "--inner-sha" in a:  # r5+: blender_inner.py changed on purpose; pin the new sha
        i = a.index("--inner-sha"); INNER_SHA = a[i + 1]; del a[i:i + 2]
    if "--evidence-dir" in a:
        i = a.index("--evidence-dir"); R4 = os.path.abspath(a[i + 1]); del a[i:i + 2]
    if "--best" in a:
        i = a.index("--best"); best = json.load(open(a[i + 1])); del a[i:i + 2]
    cand, params_p, out = a
    rep = {"candidate": os.path.relpath(cand, ROOT), "baseline_r2": BASE}
    if sha(GOLD) != GOLD_SHA: fail(2, "gold sha mismatch", out, rep)
    if sha(INNER) != INNER_SHA: fail(2, "blender_inner.py changed (defaults must stay)", out, rep)
    if 'arg("--view-transform", "Standard")' not in open(INNER).read(): fail(2, "default view_transform not Standard", out, rep)
    sp = cand + ".sha256"
    if not os.path.isfile(sp) or open(sp).read().split()[0] != sha(cand): fail(2, "candidate sha256 file missing/mismatch", out, rep)
    params = open(params_p, "rb").read()
    if b"c83a2f4a-0a3d-4494-8da9-37e6ca6943a7" in params.replace(b'"m2_id_not_used": "c83a2f4a-0a3d-4494-8da9-37e6ca6943a7"', b""):
        fail(2, "M2 id mixed into params", out, rep)
    if b"ccdaa114-cdb7-4ef5-af26-022938a780d5" not in params: fail(2, "replace_id ccdaa114 missing", out, rep)
    for dp, _, fs in os.walk(R4):
        for f in fs:
            if f.endswith((".json", ".txt", ".log", ".md", ".sha256")) and SECRET.search(open(os.path.join(dp, f), "rb").read()):
                fail(2, f"secret-like pattern in {f}", out, rep)
    gold, ours = load(GOLD), load(cand)
    if ours.shape != (1080, 1920, 3): fail(2, "candidate not 1920x1080", out, rep)
    fg = fg_mask(gold); d = np.abs(gold - ours)
    m = {"mae": round(float(d.mean()), 4), "mae_fg": round(float(d[fg].mean()), 4),
         "ssim": round(ssim_lum(gold, ours), 6), "d_lum_fg": round(float((ours[fg] @ LUM - gold[fg] @ LUM).mean()), 3)}
    rep["metrics"] = m
    ref = dict(BASE)
    if best:
        rep["best_previous"] = best["metrics"]
        ref = {k: min(ref[k], best["metrics"][k]) if k != "ssim" else max(ref[k], best["metrics"][k]) for k in ref}
    rep["must_beat"] = ref
    ok = m["mae_fg"] < ref["mae_fg"] * 0.99 and m["mae"] <= ref["mae"] and m["ssim"] >= ref["ssim"] - 0.002
    if not ok:
        fail(1, f"diff vs gold not reduced: {m} vs {ref}", out, rep)
    rep["status"] = "IMPROVED"
    json.dump(rep, open(out, "w"), indent=1)
    print("IMPROVED", json.dumps(m))


if __name__ == "__main__":
    main()
