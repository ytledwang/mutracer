#!/usr/bin/env python3
"""Usage: make_compare.py out.png crop(x0,y0,x1,y1 @960) label1=img1 label2=img2 ...  -> full row + 2x ROI row."""
import sys
from PIL import Image, ImageDraw, ImageFont
out, crop = sys.argv[1], tuple(int(v) for v in sys.argv[2].split(','))
items=[a.rsplit('=',1) for a in sys.argv[3:]]
W=960; H=540; cw,ch=crop[2]-crop[0],crop[3]-crop[1]; zs=min(W/cw, 2.0); zw,zh=int(cw*zs),int(ch*zs)
try: font=ImageFont.truetype('/System/Library/Fonts/Hiragino Sans GB.ttc',28)
except Exception: font=ImageFont.load_default()
canvas=Image.new('RGB',(len(items)*(W+12),H+zh+90),(30,30,30)); d=ImageDraw.Draw(canvas)
for k,(lab,p) in enumerate(items):
    im=Image.open(p).convert('RGB'); im=im.resize((W,round(im.height*W/im.width)),Image.LANCZOS)
    x=k*(W+12); canvas.paste(im.crop((0,0,W,H)),(x,40)); d.rectangle([x+crop[0],40+crop[1],x+crop[2],40+crop[3]],outline=(255,60,60),width=2)
    canvas.paste(im.crop(crop).resize((zw,zh),Image.NEAREST),(x,H+80)); d.text((x+8,4),lab,fill=(255,255,255),font=font)
canvas.save(out); print(out, canvas.size)
