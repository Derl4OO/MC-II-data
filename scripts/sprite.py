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
def place(kind, fill, ring, r):
    """Our places (MC-II-data sights): castle, ruins, viewpoint, motorest, waterfall."""
    s = 24*r
    im = Image.new("RGBA", (s, s), (0,0,0,0)); d = ImageDraw.Draw(im)
    d.ellipse([r, r, s-1-r, s-1-r], fill=fill, outline=ring, width=2*r)
    W = (255,255,255,255); lw = max(1, int(1.4*r))
    if kind in ("castle", "ruins"):
        d.rectangle([7*r, 10*r, 17*r, 17*r], fill=W)
        for x in (7, 11, 15):
            d.rectangle([x*r, 6*r, (x+2)*r, 10*r], fill=W)
        d.rectangle([11*r, 13*r, 13*r, 17*r], fill=fill)
        if kind == "ruins":
            d.polygon([(14*r, 7*r), (17.5*r, 7*r), (17.5*r, 12*r)], fill=fill)
    elif kind == "viewpoint":
        d.polygon([(12*r, 6*r), (18*r, 17*r), (6*r, 17*r)], fill=W)
        d.polygon([(12*r, 10.5*r), (14.2*r, 14.5*r), (9.8*r, 14.5*r)], fill=fill)
    elif kind == "motorest":
        d.line([9*r, 6*r, 9*r, 18*r], fill=W, width=lw)
        for x in (7.5, 10.5):
            d.line([x*r, 6*r, x*r, 10*r], fill=W, width=max(1, r))
        d.line([7.5*r, 10*r, 10.5*r, 10*r], fill=W, width=max(1, r))
        d.pieslice([13*r, 6*r, 17*r, 14*r], 180, 360, fill=W); d.rectangle([13*r, 10*r, 17*r, 12*r], fill=W)
        d.line([15*r, 12*r, 15*r, 18*r], fill=W, width=lw)
    elif kind == "waterfall":
        for x in (8, 12, 16):
            d.line([x*r, 6*r, x*r, 15*r], fill=W, width=lw)
        d.arc([6*r, 13*r, 18*r, 19*r], 0, 180, fill=W, width=lw)
    return im, {"width": s, "height": s, "pixelRatio": r}
def arrow(color, r):
    w, h = 14*r, 8*r
    im = Image.new("RGBA", (w, h), (0,0,0,0)); d = ImageDraw.Draw(im)
    d.line([1*r, 4*r, 10*r, 4*r], fill=color, width=max(1, int(1.4*r)))
    d.polygon([(13*r, 4*r), (8.5*r, 1*r), (8.5*r, 7*r)], fill=color)
    return im, {"width": w, "height": h, "pixelRatio": r}
def sheet(r):
    items = [("shield-main-day", shield((251,210,122,255),(179,154,120,255),r)), ("shield-day", shield((255,255,255,255),(179,163,140,255),r)),
             ("shield-main-night", shield((90,78,52,255),(217,183,104,255),r)), ("shield-night", shield((44,48,56,255),(125,130,142,255),r)),
             ("fuel-day", poi("fuel",(232,89,12,255),(255,255,255,255),r)), ("cafe-day", poi("cafe",(232,89,12,255),(255,255,255,255),r)),
             ("fuel-night", poi("fuel",(240,106,31,255),(27,30,36,255),r)), ("cafe-night", poi("cafe",(240,106,31,255),(27,30,36,255),r)),
             ("castle-day", place("castle",(139, 90, 43, 255),(255,255,255,255),r)), ("castle-night", place("castle",(139, 90, 43, 255),(31,29,27,255),r)),
             ("ruins-day", place("ruins",(128, 112, 96, 255),(255,255,255,255),r)), ("ruins-night", place("ruins",(128, 112, 96, 255),(31,29,27,255),r)),
             ("viewpoint-day", place("viewpoint",(47, 158, 68, 255),(255,255,255,255),r)), ("viewpoint-night", place("viewpoint",(47, 158, 68, 255),(31,29,27,255),r)),
             ("motorest-day", place("motorest",(232, 89, 12, 255),(255,255,255,255),r)), ("motorest-night", place("motorest",(232, 89, 12, 255),(31,29,27,255),r)),
             ("waterfall-day", place("waterfall",(28, 126, 214, 255),(255,255,255,255),r)), ("waterfall-night", place("waterfall",(28, 126, 214, 255),(31,29,27,255),r)),
             ("oneway-day", arrow((140,128,110,255),r)), ("oneway-night", arrow((150,142,130,255),r))]
    W = sum(i[1][0].width for i in items) + 2*len(items); H = max(i[1][0].height for i in items)
    out = Image.new("RGBA", (W, H), (0,0,0,0)); meta = {}; x = 0
    for name, (im, m) in items:
        out.paste(im, (x, 0)); meta[name] = dict(m, x=x, y=0); x += im.width + 2
    return out, meta
for r, suffix in ((1, ""), (2, "@2x")):
    im, meta = sheet(r); im.save(f"sprite{suffix}.png", optimize=True)
    json.dump(meta, open(f"sprite{suffix}.json", "w"))
