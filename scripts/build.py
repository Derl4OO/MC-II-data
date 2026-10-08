#!/usr/bin/env python3
"""MotoCesta data build: roads (tiles), speed cameras and fuel stations for CZ + SK.

Input: OPL files made by osmium-tool (see .github/workflows/data.yml):
  roads-*.opl   ways with node locations (osmium add-locations-to-ways)
  cams-*.opl    speed camera nodes
  fuel-*.opl    fuel nodes and ways with node locations
Output (site/v1/):
  roads/<x>_<y>.bin  raw-DEFLATE JSON array of roads per tile (0.075° lon × 0.05° lat)
  radars.json        Overpass-like {"elements": [...]} with speed cameras
  fuel.json          Overpass-like {"elements": [...]} with fuel stations (ways as "center")
  meta.json          build time and counts
Data © OpenStreetMap contributors, ODbL.
"""
import glob, json, math, os, re, sys, time, zlib
from collections import defaultdict

TILE_LAT, TILE_LON = 0.05, 0.075
KINDS = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street"}
ESC = re.compile(r"%([0-9a-fA-F]+)%")

def unescape(text):
    return ESC.sub(lambda m: chr(int(m.group(1), 16)), text)

def parse_tags(field):
    tags = {}
    if not field:
        return tags
    for pair in field.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            tags[unescape(k)] = unescape(v)
    return tags

def parse_line(line):
    """Returns (type, id, tags, extra) where extra is node coords or way node list."""
    parts = line.rstrip("\n").split(" ")
    head = parts[0]
    kind, oid = head[0], int(head[1:])
    tags, nodes, x, y = {}, None, None, None
    for p in parts[1:]:
        if not p:
            continue
        c, val = p[0], p[1:]
        if c == "T":
            tags = parse_tags(val)
        elif c == "N":
            nodes = []
            for ref in val.split(",") if val else []:
                m = re.match(r"n(-?\d+)(?:x(-?[\d.]+)y(-?[\d.]+))?", ref)
                if m:
                    nodes.append((int(m.group(1)),
                                  float(m.group(2)) if m.group(2) else None,
                                  float(m.group(3)) if m.group(3) else None))
        elif c == "x":
            x = float(val) if val else None
        elif c == "y":
            y = float(val) if val else None
    return kind, oid, tags, nodes if kind == "w" else (x, y)

def speed_limit(tags, kind):
    for key in ("maxspeed", "maxspeed:type", "source:maxspeed"):
        raw = tags.get(key, "").lower()
        if not raw:
            continue
        first = raw.split(" ")[0]
        if first.isdigit() and int(first) > 0:
            return int(int(first) * 1.609) if "mph" in raw else int(first)
        if raw.endswith(":urban"): return 50
        if raw.endswith(":rural"): return 90
        if raw.endswith(":motorway"): return 130
        if raw.endswith(":living_street"): return 20
    return {"motorway": 130, "living_street": 20}.get(kind)

def oneway(tags, kind):
    v = tags.get("oneway")
    if v in ("yes", "1", "true"): return 1
    if v in ("-1", "reverse"): return -1
    if v in ("no", "0", "false"): return 0
    return 1 if kind in ("motorway", "motorway_link") or tags.get("junction") == "roundabout" else 0

def tiles_for(lats, lons):
    keys = set()
    for i in range(len(lats)):
        keys.add((math.floor(lons[i] / TILE_LON), math.floor(lats[i] / TILE_LAT)))
        if i:
            # long segments (motorways) may cross a tile without a point in it
            steps = int(max(abs(lats[i] - lats[i-1]) / TILE_LAT, abs(lons[i] - lons[i-1]) / TILE_LON) * 2)
            for s in range(1, steps + 1):
                t = s / (steps + 1)
                la = lats[i-1] + (lats[i] - lats[i-1]) * t
                lo = lons[i-1] + (lons[i] - lons[i-1]) * t
                keys.add((math.floor(lo / TILE_LON), math.floor(la / TILE_LAT)))
    return keys

def build_roads(files, out_dir):
    tiles = defaultdict(dict)  # tile -> {way id: json}
    count = 0
    for path in files:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.startswith("w"):
                    continue
                _, wid, tags, nodes = parse_line(line)
                kind = tags.get("highway", "")
                if kind.replace("_link", "") not in KINDS or not nodes or len(nodes) < 2:
                    continue
                if any(n[1] is None or n[2] is None for n in nodes):
                    continue
                lats = [round(n[2], 6) for n in nodes]
                lons = [round(n[1], 6) for n in nodes]
                road = json.dumps({"id": wid, "nodes": [n[0] for n in nodes], "lats": lats, "lons": lons,
                                   "kind": kind, "limit": speed_limit(tags, kind), "oneway": oneway(tags, kind)},
                                  separators=(",", ":"))
                for key in tiles_for(lats, lons):
                    tiles[key][wid] = road
                count += 1
    os.makedirs(os.path.join(out_dir, "roads"), exist_ok=True)
    for (x, y), roads in tiles.items():
        payload = ("[" + ",".join(roads.values()) + "]").encode("utf-8")
        compressor = zlib.compressobj(9, zlib.DEFLATED, -15)  # raw DEFLATE for Apple's .zlib
        with open(os.path.join(out_dir, "roads", f"{x}_{y}.bin"), "wb") as f:
            f.write(compressor.compress(payload) + compressor.flush())
    return count, len(tiles)

def build_points(files, out_path, want):
    elements, seen = [], set()
    for path in files:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line or line[0] not in "nw":
                    continue
                kind, oid, tags, extra = parse_line(line)
                if not want(tags) or (kind, oid) in seen:
                    continue
                seen.add((kind, oid))
                if kind == "n":
                    x, y = extra
                    if x is None or y is None:
                        continue
                    elements.append({"type": "node", "id": oid, "lat": y, "lon": x, "tags": tags})
                else:
                    pts = [(n[1], n[2]) for n in extra or [] if n[1] is not None and n[2] is not None]
                    if not pts:
                        continue
                    lon = sum(p[0] for p in pts) / len(pts)
                    lat = sum(p[1] for p in pts) / len(pts)
                    elements.append({"type": "way", "id": oid, "center": {"lat": lat, "lon": lon}, "tags": tags})
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"elements": elements}, f, ensure_ascii=False, separators=(",", ":"))
    return len(elements)

def main(work, site):
    out = os.path.join(site, "v1")
    os.makedirs(out, exist_ok=True)
    roads, tiles = build_roads(sorted(glob.glob(os.path.join(work, "roads-*.opl"))), out)
    cams = build_points(sorted(glob.glob(os.path.join(work, "cams-*.opl"))), os.path.join(out, "radars.json"),
                        lambda t: t.get("highway") == "speed_camera")
    fuel = build_points(sorted(glob.glob(os.path.join(work, "fuel-*.opl"))), os.path.join(out, "fuel.json"),
                        lambda t: t.get("amenity") == "fuel")
    meta = {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "roads": roads, "tiles": tiles,
            "speedCameras": cams, "fuelStations": fuel, "license": "© OpenStreetMap contributors, ODbL 1.0"}
    with open(os.path.join(out, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    with open(os.path.join(site, "index.html"), "w", encoding="utf-8") as f:
        f.write("<!doctype html><meta charset=utf-8><title>MotoCesta data</title>"
                "<p>Data pro aplikaci MotoCesta z OpenStreetMap (ČR + SK). "
                "© <a href='https://www.openstreetmap.org/copyright'>přispěvatelé OpenStreetMap</a>, ODbL.</p>"
                f"<pre>{json.dumps(meta, indent=1, ensure_ascii=False)}</pre>")
    print(json.dumps(meta, indent=1))
    if roads == 0 or cams == 0 or fuel == 0:
        sys.exit("Některá data chybí – nasazení zastaveno.")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
