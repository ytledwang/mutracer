#!/usr/bin/env python3
"""Noise metric at common scale (resize to --width, LANCZOS).
Region: fridge interior / door ROI (crop box in 960x540 coords) or full frame.
residual = Y - GaussBlur(Y,1.0); flat pixels = smoothed-gradient < 1.5 and 8<Y<250.
Reports: mean|res| on flat px, p99|res| (speckle/firefly), speckle_frac = share of flat px with |res|>12.
Units: 8-bit luminance levels."""
import sys, json, argparse, numpy as np
from PIL import Image, ImageFilter
def metric(p, w=960, crop=None):
    im = Image.open(p).convert('RGB')
    im = im.resize((w, round(im.height*w/im.width)), Image.LANCZOS)
    if crop: im = im.crop(crop)
    L = im.convert('L'); Y = np.asarray(L, np.float32)
    B = np.asarray(L.filter(ImageFilter.GaussianBlur(1.0)), np.float32)
    S = np.asarray(L.filter(ImageFilter.GaussianBlur(4)), np.float32)
    gy, gx = np.gradient(S); g = np.hypot(gx, gy)
    m = (g < 1.5) & (Y > 8) & (Y < 250)
    r = np.abs(Y - B)[m]
    if r.size < 200: return dict(img=p, flat_px=int(r.size))
    return dict(img=p, flat_px=int(r.size), mean_abs=round(float(r.mean()),2),
                p99=round(float(np.percentile(r,99)),1), speckle_pct=round(100*float((r>12).mean()),2))
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('imgs',nargs='+'); ap.add_argument('--width',type=int,default=960)
    ap.add_argument('--crop',type=lambda s: tuple(int(x) for x in s.split(',')))
    a=ap.parse_args()
    for p in a.imgs: print(json.dumps(metric(p,a.width,a.crop),ensure_ascii=False))
