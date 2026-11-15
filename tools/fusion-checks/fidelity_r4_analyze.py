#!/usr/bin/env python3
"""r4 grey-look diagnosis: per-region stats + per-channel global curve fit gold<-ours.
Usage: fidelity_r4_analyze.py GOLD_1920.png RENDER.png OUT.json"""
import json, sys
import numpy as np
from PIL import Image

# Regions in 1920x1080 pixel coords (x0,y0,x1,y1), Front 858db55c framing.
REGIONS = {
    "interior_cavity": (735, 105, 1045, 345),
    "crisper_bins": (715, 360, 1060, 545),
    "drawers": (685, 595, 1092, 985),
    "door_left_inner": (600, 60, 700, 550),
    "door_right_inner": (1075, 60, 1185, 550),
}
LUM = np.array([0.2126, 0.7152, 0.0722])


def load(p):
    im = Image.open(p).convert("RGB")
    if im.size != (1920, 1080):
        im = im.resize((1920, 1080), Image.LANCZOS)
    return np.asarray(im).astype(np.float64)


def fg_mask(gold):
    lum = gold @ LUM
    h, w = lum.shape
    border = np.concatenate([lum[:8].ravel(), lum[-8:].ravel(), lum[:, :8].ravel(), lum[:, -8:].ravel()])
    return np.abs(lum - np.median(border)) > 12


def ssim_lum(a, b):
    from numpy.lib.stride_tricks import sliding_window_view as sw
    x = a @ LUM; y = b @ LUM
    C1 = (0.01 * 255) ** 2; C2 = (0.03 * 255) ** 2
    def m(z): return sw(z, (11, 11)).mean(axis=(-1, -2))
    mx, my = m(x), m(y)
    vx = m(x * x) - mx ** 2; vy = m(y * y) - my ** 2; cxy = m(x * y) - mx * my
    s = ((2 * mx * my + C1) * (2 * cxy + C2)) / ((mx ** 2 + my ** 2 + C1) * (vx + vy + C2))
    return float(s.mean())


def stats(px):
    if px.size == 0:
        return None
    lum = px @ LUM
    return {
        "n": int(px.shape[0]),
        "mean_rgb": [round(float(v), 2) for v in px.mean(axis=0)],
        "mean_lum": round(float(lum.mean()), 2),
        "p5_p50_p95_lum": [round(float(np.percentile(lum, q)), 1) for q in (5, 50, 95)],
        "chroma_r_minus_b": round(float((px[:, 0] - px[:, 2]).mean()), 2),
        "hist16_lum": np.histogram(lum, bins=16, range=(0, 256))[0].tolist(),
    }


def fit_lut(src, dst, mask):
    """Per-channel monotone LUT dst<-src fitted on mask (binned mean + cummax)."""
    luts = []
    for c in range(3):
        s = src[..., c][mask].astype(int); d = dst[..., c][mask]
        sums = np.bincount(s, weights=d, minlength=256); cnt = np.bincount(s, minlength=256)
        lut = np.full(256, np.nan); ok = cnt > 0; lut[ok] = sums[ok] / cnt[ok]
        idx = np.arange(256); lut = np.interp(idx, idx[ok], lut[ok])
        luts.append(np.maximum.accumulate(lut))
    return np.stack(luts)


def apply_lut(img, luts):
    out = np.empty_like(img)
    for c in range(3):
        out[..., c] = luts[c][np.clip(img[..., c], 0, 255).astype(int)]
    return out


def fit_gain_gamma(src, dst, mask):
    """dst = 255*(gain*(src/255))**g, per channel, least squares in log on fg (src,dst>2)."""
    res = []
    for c in range(3):
        s = src[..., c][mask] / 255; d = dst[..., c][mask] / 255
        ok = (s > 0.01) & (d > 0.01) & (d < 0.995)
        A = np.stack([np.log(s[ok]), np.ones(ok.sum())], 1)
        g, lg = np.linalg.lstsq(A, np.log(d[ok]), rcond=None)[0]
        res.append((float(g), float(np.exp(lg))))
    return res


def main():
    gold, ours, out = load(sys.argv[1]), load(sys.argv[2]), sys.argv[3]
    fg = fg_mask(gold)
    diff = np.abs(gold - ours)
    rep = {
        "global": {"mae": round(float(diff.mean()), 4), "ssim": round(ssim_lum(gold, ours), 6),
                   "mae_fg": round(float(diff[fg].mean()), 4),
                   "d_lum_fg": round(float((ours[fg] @ LUM - gold[fg] @ LUM).mean()), 3),
                   "fg_px": int(fg.sum())},
        "regions": {},
    }
    bg = ~fg
    rep["regions"]["background"] = {"gold": stats(gold[bg]), "ours": stats(ours[bg]), "mae": round(float(diff[bg].mean()), 3)}
    for name, (x0, y0, x1, y1) in REGIONS.items():
        m = np.zeros(fg.shape, bool); m[y0:y1, x0:x1] = True; m &= fg
        rep["regions"][name] = {"box": [x0, y0, x1, y1], "gold": stats(gold[m]), "ours": stats(ours[m]),
                                "mae": round(float(diff[m].mean()), 3),
                                "d_lum": round(float((ours[m] @ LUM - gold[m] @ LUM).mean()), 2)}
    luts = fit_lut(ours, gold, fg)
    mapped = apply_lut(ours, luts)
    md = np.abs(gold - mapped)
    gg = fit_gain_gamma(ours, gold, fg)
    rep["global_curve_fit"] = {
        "method": "per-channel monotone LUT gold<-ours fitted on gold foreground (upper bound of any global tone/exposure curve)",
        "mae_fg_before": rep["global"]["mae_fg"], "mae_fg_after_lut": round(float(md[fg].mean()), 4),
        "mae_after_lut": round(float(md.mean()), 4), "ssim_after_lut": round(ssim_lum(gold, mapped), 6),
        "residual_fraction_fg": round(float(md[fg].mean() / diff[fg].mean()), 4),
        "region_mae_after_lut": {},
        "lut_samples_R_G_B_at_[32,64,128,192,224,250]": [[round(float(l[i]), 1) for i in (32, 64, 128, 192, 224, 250)] for l in luts],
        "gain_gamma_per_channel": [{"gamma": round(g, 4), "gain": round(k, 4)} for g, k in gg],
    }
    for name, (x0, y0, x1, y1) in REGIONS.items():
        m = np.zeros(fg.shape, bool); m[y0:y1, x0:x1] = True; m &= fg
        rep["global_curve_fit"]["region_mae_after_lut"][name] = round(float(md[m].mean()), 3)
    json.dump(rep, open(out, "w"), ensure_ascii=False, indent=1)
    if len(sys.argv) > 4:
        Image.fromarray(np.clip(mapped, 0, 255).astype(np.uint8)).save(sys.argv[4])
    print(json.dumps({k: rep[k] for k in ("global",)}), json.dumps({k: v for k, v in rep["global_curve_fit"].items() if k != "region_mae_after_lut"}))
    for n, r in rep["regions"].items():
        print(n, "gold", r["gold"]["mean_rgb"], r["gold"]["p5_p50_p95_lum"], "ours", r["ours"]["mean_rgb"], r["ours"]["p5_p50_p95_lum"], "mae", r["mae"], "after_lut", rep["global_curve_fit"]["region_mae_after_lut"].get(n))


if __name__ == "__main__":
    main()
