"""MotoCesta map layer of our own: curvy roads (two levels) and our places, as vector tiles for MapLibre.

- "curves": stretches of trunk / primary / secondary / tertiary / unclassified roads with many bends.
  Bends are found the same way as in the apps (MotoCurveDetector: points every 20 m, circle through
  points 40 m apart, a bend = radius under 150 m, sharp = under 60 m). Bends per km over a 2 km window:
  l=1 (light orange) from LEVEL1, l=2 (sharper red) from LEVEL2.
- "places": castles, chateaux, ruins, viewpoints, waterfalls and motorests from sights.json.

Output: v1/moto/{z}/{x}/{y}.pbf, zoom 8–12 (MapLibre overzooms 12 for closer views). Mapbox Vector Tile
format written here by hand (no tippecanoe, no extra packages). Data © OpenStreetMap contributors, ODbL.
"""
import glob
import json
import math
import os
import sys

LEVEL1, LEVEL2 = 3.0, 6.0  # bends per km (window 2 km)
KINDS = {"trunk", "primary", "secondary", "tertiary", "unclassified"}
PLACES = {"castle": "castle", "chateau": "castle", "ruins": "ruins", "viewpoint": "viewpoint",
          "waterfall": "waterfall", "motorest": "motorest"}
ZOOMS = range(8, 13)
EXTENT, BUFFER = 4096, 64
STEP = 20.0


# --- curves -----------------------------------------------------------------------------------------------
def _xy(points):
    lat0 = points[0][1]
    k = math.cos(math.radians(lat0)) * 111320.0
    return [((lon - points[0][0]) * k, (lat - lat0) * 110540.0) for lon, lat in points], k


def _resample(xy):
    out, carried = [xy[0]], 0.0
    index = [0]
    for i, (a, b) in enumerate(zip(xy, xy[1:])):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg <= 0:
            continue
        pos = STEP - carried
        while pos <= seg:
            t = pos / seg
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            index.append(i)
            pos += STEP
        carried = seg - (pos - STEP)
    return out


def _radius(a, b, c):
    ab = math.hypot(b[0] - a[0], b[1] - a[1])
    bc = math.hypot(c[0] - b[0], c[1] - b[1])
    ac = math.hypot(c[0] - a[0], c[1] - a[1])
    cross = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
    return float("inf") if cross < 1e-6 else ab * bc * ac / (2 * cross)


def curvy_runs(points):
    """[(level, [(lon, lat), ...]), ...] for one road."""
    xy, k = _xy(points)
    samples = _resample(xy)
    n = len(samples)
    if n < 30:  # under 600 m: too short to judge on its own
        return []
    centers = []
    start, tightest = None, float("inf")
    for i in range(2, n - 2):
        r = _radius(samples[i - 2], samples[i], samples[i + 2])
        if r < 150:
            if start is None:
                start, tightest = i, r
            tightest = min(tightest, r)
        elif start is not None:
            centers.append(((start + i - 1) // 2, tightest < 60))
            start = None
    if start is not None:
        centers.append(((start + n - 3) // 2, tightest < 60))
    if not centers:
        return []
    # bends per km in a window of +-1 km (50 samples), sharp bends count 1.5x
    weight = [0.0] * n
    for c, sharp in centers:
        weight[c] += 1.5 if sharp else 1.0
    prefix = [0.0]
    for w in weight:
        prefix.append(prefix[-1] + w)
    levels = []
    for i in range(n):
        a, b = max(0, i - 50), min(n, i + 51)
        km = max((b - a) * STEP / 1000, 0.6)
        rate = (prefix[b] - prefix[a]) / km
        levels.append(2 if rate >= LEVEL2 else 1 if rate >= LEVEL1 else 0)
    runs, i = [], 0
    while i < n:
        if levels[i] == 0:
            i += 1
            continue
        j = i
        while j + 1 < n and levels[j + 1] == levels[i]:
            j += 1
        if (j - i) * STEP >= 300:
            lon0, lat0 = points[0]
            coords = [(lon0 + x / k, lat0 + y / 110540.0) for x, y in samples[i:j + 1]]
            runs.append((levels[i], coords))
        i = j + 1
    return runs


def read_curves(work):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from build import parse_line  # same OPL reader as the road data
    runs = []
    for path in sorted(glob.glob(os.path.join(work, "roads-*.opl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.startswith("w"):
                    continue
                _, _, tags, nodes = parse_line(line)
                if tags.get("highway") not in KINDS or not nodes or len(nodes) < 3:
                    continue
                if any(node[1] is None for node in nodes):
                    continue
                runs += curvy_runs([(node[1], node[2]) for node in nodes])
    return runs


# --- Mapbox Vector Tile encoding --------------------------------------------------------------------------
def _varint(value):
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _key(field, wire):
    return _varint((field << 3) | wire)


def _bytes(field, data):
    return _key(field, 2) + _varint(len(data)) + data


def _packed(field, values):
    return _bytes(field, b"".join(_varint(v) for v in values))


def _zigzag(n):
    return (n << 1) ^ (n >> 31)


def _geometry(kind, parts):
    out, cx, cy = [], 0, 0
    for part in parts:
        x, y = part[0]
        out += [1 | (1 << 3), _zigzag(x - cx), _zigzag(y - cy)]
        cx, cy = x, y
        if kind == 2:
            rest = part[1:]
            out.append(2 | (len(rest) << 3))
            for x, y in rest:
                out += [_zigzag(x - cx), _zigzag(y - cy)]
                cx, cy = x, y
    return out


def _layer(name, features):
    """features: [(type 1|2, parts, {key: value})]"""
    keys, values, body = [], [], b""
    for kind, parts, props in features:
        tags = []
        for k, v in props.items():
            if k not in keys:
                keys.append(k)
            if v not in values:
                values.append(v)
            tags += [keys.index(k), values.index(v)]
        feature = _packed(2, tags) + _key(3, 0) + _varint(kind) + _packed(4, _geometry(kind, parts))
        body += _bytes(2, feature)
    for k in keys:
        body += _bytes(3, k.encode("utf-8"))
    for v in values:
        value = _key(4, 0) + _varint(v) if isinstance(v, int) else _bytes(1, str(v).encode("utf-8"))
        body += _bytes(4, value)
    return _bytes(3, _key(15, 0) + _varint(2) + _bytes(1, name.encode()) + body + _key(5, 0) + _varint(EXTENT))


# --- tiling -----------------------------------------------------------------------------------------------
def _world(lon, lat, z):
    scale = EXTENT * (1 << z)
    x = (lon + 180) / 360 * scale
    s = math.sin(math.radians(max(min(lat, 85), -85)))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * scale
    return x, y


def _simplify(points, tolerance):
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy) or 1e-9
        best, index = 0.0, None
        for i in range(a + 1, b):
            d = abs(dy * (points[i][0] - ax) - dx * (points[i][1] - ay)) / length
            if d > best:
                best, index = d, i
        if index is not None and best > tolerance:
            keep[index] = True
            stack += [(a, index), (index, b)]
    return [p for p, k in zip(points, keep) if k]


def _clip(points, lo, hi):
    """Liang–Barsky clip of a polyline to the square [lo, hi]; returns the pieces inside."""
    pieces, current = [], []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        t0, t1, dx, dy = 0.0, 1.0, x1 - x0, y1 - y0
        ok = True
        for p, q in ((-dx, x0 - lo), (dx, hi - x0), (-dy, y0 - lo), (dy, hi - y0)):
            if p == 0:
                if q < 0:
                    ok = False
                    break
            else:
                t = q / p
                if p < 0:
                    t0 = max(t0, t)
                else:
                    t1 = min(t1, t)
        if not ok or t0 > t1:
            if len(current) > 1:
                pieces.append(current)
            current = []
            continue
        a = (x0 + dx * t0, y0 + dy * t0)
        b = (x0 + dx * t1, y0 + dy * t1)
        if not current:
            current = [a]
        current.append(b)
        if t1 < 1:
            pieces.append(current)
            current = []
    if len(current) > 1:
        pieces.append(current)
    return pieces


def build_tiles(runs, places, out_dir):
    tiles = {}
    for z in ZOOMS:
        tolerance = 6 if z < 12 else 3
        for level, coords in runs:
            world = _simplify([_world(lon, lat, z) for lon, lat in coords], tolerance)
            xs, ys = [p[0] for p in world], [p[1] for p in world]
            for tx in range(int((min(xs) - BUFFER) // EXTENT), int((max(xs) + BUFFER) // EXTENT) + 1):
                for ty in range(int((min(ys) - BUFFER) // EXTENT), int((max(ys) + BUFFER) // EXTENT) + 1):
                    local = [(x - tx * EXTENT, y - ty * EXTENT) for x, y in world]
                    for piece in _clip(local, -BUFFER, EXTENT + BUFFER):
                        part, last = [], None
                        for x, y in piece:
                            q = (int(round(x)), int(round(y)))
                            if q != last:
                                part.append(q)
                                last = q
                        if len(part) > 1:
                            tiles.setdefault((z, tx, ty), ([], []))[0].append((2, [part], {"l": level}))
        if z >= 10:
            for lon, lat, name, kind in places:
                x, y = _world(lon, lat, z)
                tx, ty = int(x // EXTENT), int(y // EXTENT)
                point = (int(round(x - tx * EXTENT)), int(round(y - ty * EXTENT)))
                tiles.setdefault((z, tx, ty), ([], []))[1].append((1, [[point]], {"k": kind, "n": name}))
    for (z, x, y), (lines, points) in tiles.items():
        data = (_layer("curves", lines) if lines else b"") + (_layer("places", points) if points else b"")
        folder = os.path.join(out_dir, "moto", str(z), str(x))
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, f"{y}.pbf"), "wb") as f:
            f.write(data)
    return len(tiles)


def main(work, out):
    runs = read_curves(work)
    km = {1: 0.0, 2: 0.0}
    for level, coords in runs:
        km[level] += (len(coords) - 1) * STEP / 1000
    places = []
    try:
        with open(os.path.join(out, "sights.json"), encoding="utf-8") as f:
            for lat, lon, name, kind in json.load(f)["sights"]:
                if kind in PLACES:
                    places.append((lon, lat, name, PLACES[kind]))
    except (OSError, ValueError, KeyError) as error:
        print("::warning::Místa pro mapu chybí:", error)
    count = build_tiles(runs, places, out)
    print("Zatáčky na mapě: %d km lehčích, %d km ostřejších, %d míst, %d dlaždic" % (km[1], km[2], len(places), count))
    return {"curvesKm": {"light": round(km[1]), "sharp": round(km[2])}, "places": len(places), "tiles": count}


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
