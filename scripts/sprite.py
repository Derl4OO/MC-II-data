"""MotoCesta map sprite: road number shields and rider place icons, drawn by Claude (own artwork). Needs Pillow; run in style-assets/: python3 ../scripts/sprite.py"""
from PIL import Image, ImageDraw
import json, sys
def shield(fill, border, r):
    w, h = 26*r, 20*r
    im = Image.new("RGBA", (w, h), (0,0,0,0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([r, r, w-1-r, h-1-r], radius=4*r, fill=fill, outline=border, width=max(1, int(1.5*r)))
    return im, {"width": w, "height": h, "pixelRatio": r, "stretchX": [[7*r, 19*r]], "stretchY": [[7*r, 13*r]], "content": [5*r, 4*r, 21*r, 16*r]}
def poi(kind, fill, ring, r):
    s = 24*r
    im = Image.new("RGBA", (s, s), (0,0,0,0)); d = ImageDraw.Draw(im)
    d.ellipse([r, r, s-1-r, s-1-r], fill=fill, outline=ring, width=2*r)
    W = (255,255,255,255)
    if kind == "fuel":
        d.rounded_rectangle([7*r, 6*r, 14*r, 18*r], radius=1*r, fill=W)       # pump
        d.rectangle([8.5*r, 7.5*r, 12.5*r, 10.5*r], fill=fill)                # window
        d.line([14*r, 9*r, 16.5*r, 11*r, 16.5*r, 16*r, 17.5*r, 16*r, 17.5*r, 9*r], fill=W, width=max(1, int(1.3*r)))
    else:
        d.rounded_rectangle([6.5*r, 9*r, 15*r, 16.5*r], radius=2*r, fill=W)    # cup
        d.ellipse([14*r, 10*r, 18*r, 14*r], outline=W, width=max(1, int(1.4*r)))
        d.line([8*r, 6*r, 8*r, 7.5*r], fill=W, width=r); d.line([11*r, 5.5*r, 11*r, 7.5*r], fill=W, width=r)
    return im, {"width": s, "height": s, "pixelRatio": r}
def sheet(r):
    items = [("shield-main-day", shield((251,210,122,255),(179,154,120,255),r)), ("shield-day", shield((255,255,255,255),(179,163,140,255),r)),
             ("shield-main-night", shield((90,78,52,255),(217,183,104,255),r)), ("shield-night", shield((44,48,56,255),(125,130,142,255),r)),
             ("fuel-day", poi("fuel",(232,89,12,255),(255,255,255,255),r)), ("cafe-day", poi("cafe",(232,89,12,255),(255,255,255,255),r)),
             ("fuel-night", poi("fuel",(240,106,31,255),(27,30,36,255),r)), ("cafe-night", poi("cafe",(240,106,31,255),(27,30,36,255),r))]
    W = sum(i[1][0].width for i in items) + 2*len(items); H = max(i[1][0].height for i in items)
    out = Image.new("RGBA", (W, H), (0,0,0,0)); meta = {}; x = 0
    for name, (im, m) in items:
        out.paste(im, (x, 0)); meta[name] = dict(m, x=x, y=0); x += im.width + 2
    return out, meta
for r, suffix in ((1, ""), (2, "@2x")):
    im, meta = sheet(r); im.save(f"sprite{suffix}.png", optimize=True)
    json.dump(meta, open(f"sprite{suffix}.json", "w"))
