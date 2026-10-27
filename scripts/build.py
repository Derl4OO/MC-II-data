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
  sights.json        {"sights": [[lat, lon, name, kind], ...]} named castles, chateaux, ruins, viewpoints,
                     mountain passes, waterfalls, peaks, cafés and motorests for "Překvap mě" (extracted here from <cc>.osm.pbf with osmium,
                     so the workflow file does not need to change)
  meta.json          build time and counts
Data © OpenStreetMap contributors, ODbL.
"""
import glob, json, math, os, re, subprocess, sys, time, unicodedata, zlib
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
    # Order: the posted limit, then its legal type ("CZ:urban"), then the traffic zone the road lies in
    # ("zone:traffic=CZ:rural", "zone:maxspeed=CZ:50"). A direction-only limit counts when both sides agree
    # or only one side is given (the app has no per-direction limits yet).
    fw, bw = tags.get("maxspeed:forward", ""), tags.get("maxspeed:backward", "")
    if not tags.get("maxspeed") and (fw or bw) and (not fw or not bw or fw == bw):
        tags = dict(tags, maxspeed=fw or bw)
    for key in ("maxspeed", "maxspeed:type", "source:maxspeed", "zone:maxspeed", "zone:traffic"):
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

# --- Default (implied) limits for roads without a maxspeed tag (Czech/Slovak rules) ---
# Most rural roads in OSM have no maxspeed; the law gives 90 outside and 50 inside built-up areas.
# Built-up areas are approximated by OSM landuse polygons (residential, retail, commercial),
# rasterised into ~100 m cells.
CELL_LAT, CELL_LON = 0.0009, 0.0013
URBAN_FILTER = ["w/landuse=residential,retail,commercial"]

def extract_urban(work):
    for pbf in sorted(glob.glob("*.osm.pbf")):
        c = os.path.basename(pbf).split(".")[0]
        try:
            subprocess.run(["osmium", "tags-filter", pbf, *URBAN_FILTER, "-o", f"urban-{c}.pbf", "--overwrite"], check=True)
            subprocess.run(["osmium", "add-locations-to-ways", f"urban-{c}.pbf", "-f", "opl,add_metadata=false",
                            "-o", os.path.join(work, f"urban-{c}.opl"), "--overwrite"], check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            print("Zástavbu se nepodařilo vybrat:", error)

def build_urban_cells(work):
    cells = set()
    for path in sorted(glob.glob(os.path.join(work, "urban-*.opl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.startswith("w"):
                    continue
                _, _, tags, nodes = parse_line(line)
                pts = [(n[1], n[2]) for n in nodes or [] if n[1] is not None and n[2] is not None]
                if len(pts) < 4 or pts[0] != pts[-1]:
                    continue  # only closed areas
                lons = [p[0] for p in pts]; lats = [p[1] for p in pts]
                x0, x1 = math.floor(min(lons) / CELL_LON), math.floor(max(lons) / CELL_LON)
                y0, y1 = math.floor(min(lats) / CELL_LAT), math.floor(max(lats) / CELL_LAT)
                if (x1 - x0 + 1) * (y1 - y0 + 1) > 40000:
                    continue  # absurdly large area (mapping error)
                # Scanline fill: for each cell row, the edge crossings at the row's centre line.
                edges = list(zip(pts, pts[1:]))
                for cy in range(y0, y1 + 1):
                    py = (cy + 0.5) * CELL_LAT
                    xs = sorted(xi + (py - yi) * (xj - xi) / (yj - yi)
                                for (xi, yi), (xj, yj) in edges if (yi > py) != (yj > py))
                    for k in range(0, len(xs) - 1, 2):
                        for cx in range(math.floor(xs[k] / CELL_LON - 0.5) + 1, math.floor(xs[k + 1] / CELL_LON - 0.5) + 1):
                            cells.add((cx, cy))
                # small areas: make sure the polygon's own corners count too
                for lo, la in pts:
                    cells.add((math.floor(lo / CELL_LON), math.floor(la / CELL_LAT)))
    return cells

# --- Village / town signs (start and end of a built-up area) ---
# The legal 50 km/h starts exactly at the sign, so where landuse says the road enters or leaves a built-up
# area and such a sign stands within 400 m along the road, the change is moved to the sign.
# CZ: IS 12a/12b, SK: IS 36/IS 37, everywhere also traffic_sign=city_limit.
SIGN_RE = re.compile(r"city_limit|IS ?12[ab]|IS ?3[67]", re.I)
CITY_LIMITS = defaultdict(list)  # cell -> [(lon, lat)]
SIGN_CELL = 0.002

def extract_city_limits(work):
    for pbf in sorted(glob.glob("*.osm.pbf")):
        c = os.path.basename(pbf).split(".")[0]
        try:
            subprocess.run(["osmium", "tags-filter", pbf, "n/traffic_sign", "-f", "opl,add_metadata=false",
                            "-o", os.path.join(work, f"signs-{c}.opl"), "--overwrite"], check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            print("Značky obcí se nepodařilo vybrat:", error)

def load_city_limits(work):
    count = 0
    for path in sorted(glob.glob(os.path.join(work, "signs-*.opl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.startswith("n"):
                    continue
                _, _, tags, (x, y) = parse_line(line)
                if x is None or y is None:
                    continue
                values = " ".join(v for k, v in tags.items() if k.startswith("traffic_sign"))
                if SIGN_RE.search(values):
                    CITY_LIMITS[(math.floor(x / SIGN_CELL), math.floor(y / SIGN_CELL))].append((x, y))
                    count += 1
    return count

def near_city_limit(lon, lat, meters=30):
    cx, cy = math.floor(lon / SIGN_CELL), math.floor(lat / SIGN_CELL)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for (x, y) in CITY_LIMITS.get((cx + dx, cy + dy), ()):
                if distance_m(lon, lat, x, y) <= meters:
                    return True
    return False

def distance_m(lon1, lat1, lon2, lat2):
    dx = (lon2 - lon1) * 111320 * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat2 - lat1) * 110540
    return math.hypot(dx, dy)

def snap_to_signs(flags, lons, lats, reach=400):
    """Moves each urban/rural change to a village sign within `reach` metres along the road."""
    if not CITY_LIMITS:
        return flags
    flags = list(flags)
    n = len(flags)
    along = [0.0]
    for i in range(1, n):
        along.append(along[-1] + distance_m(lons[i - 1], lats[i - 1], lons[i], lats[i]))
    signs = [i for i in range(n) if near_city_limit(lons[i], lats[i])]
    if not signs:
        return flags
    for i in range(1, n):
        if flags[i] == flags[i - 1]:
            continue
        best = min(signs, key=lambda j: abs(along[j] - along[i]))
        if abs(along[best] - along[i]) > reach or best == i:
            continue
        if best < i:
            for k in range(best, i):
                flags[k] = flags[i]
        else:
            for k in range(i, best):
                flags[k] = flags[i - 1]
    return flags

def is_urban(cells, lon, lat):
    cx, cy = math.floor(lon / CELL_LON), math.floor(lat / CELL_LAT)
    return any((cx + dx, cy + dy) in cells for dx in (-1, 0, 1) for dy in (-1, 0, 1))

def implied_limit(tags, kind, urban):
    base = kind.replace("_link", "")
    if base == "motorway": return 130
    if base == "living_street": return 20
    if base == "residential": return 50
    if base == "trunk" and tags.get("motorroad") == "yes" and not urban: return 110
    return 50 if urban else 90

URBAN_CELLS = set()
# Quality check written to meta.json: road pieces with a posted limit, with a default limit, and without any.
LIMIT_STATS = {"signed": 0, "implied": 0, "none": 0}

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
                limit = speed_limit(tags, kind)
                # "signed": the limit is posted in OSM (sign, zone), not just the road-class default.
                signed = speed_limit(tags, "") is not None
                if limit is not None or not URBAN_CELLS:
                    pieces = [(0, len(nodes) - 1, limit)]
                else:
                    # No tag: implied limit, split where the road enters or leaves a built-up area
                    # (pieces share the node, so the road network stays connected).
                    flags = snap_to_signs([is_urban(URBAN_CELLS, lons[i], lats[i]) for i in range(len(nodes))], lons, lats)
                    pieces, start = [], 0
                    for i in range(1, len(nodes)):
                        if i == len(nodes) - 1 or flags[i] != flags[start]:
                            pieces.append((start, i, implied_limit(tags, kind, flags[start])))
                            start = i
                for k, (a, b, piece_limit) in enumerate(pieces):
                    pid = wid if len(pieces) == 1 else wid * 100 + k
                    piece = {"id": pid, "nodes": [n[0] for n in nodes[a:b + 1]], "lats": lats[a:b + 1], "lons": lons[a:b + 1],
                             "kind": kind, "limit": piece_limit, "oneway": oneway(tags, kind)}
                    if signed:
                        piece["signed"] = True  # JSON true (Swift Bool decodes only true/false)
                    LIMIT_STATS["none" if piece_limit is None else "signed" if signed else "implied"] += 1
                    road = json.dumps(piece, separators=(",", ":"))
                    for key in tiles_for(lats[a:b + 1], lons[a:b + 1]):
                        tiles[key][pid] = road
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

SIGHT_FILTERS = ["nw/historic=castle,ruins", "nw/tourism=viewpoint", "n/mountain_pass=yes",
                 "n/natural=waterfall,peak", "nw/amenity=cafe,restaurant"]

# Restaurants only when the name says it is a roadside stop for riders/drivers (motorest, motel, bikers).
MOTOREST_RE = re.compile(r"motorest|motel|biker|motork[aá]ř|moto ?caf|moto ?bar", re.I)

def extract_sights(work):
    """Runs osmium on the downloaded country files (cz.osm.pbf, sk.osm.pbf in the current folder)."""
    for pbf in sorted(glob.glob("*.osm.pbf")):
        c = os.path.basename(pbf).split(".")[0]
        try:
            subprocess.run(["osmium", "tags-filter", pbf, *SIGHT_FILTERS, "-o", f"sights-{c}.pbf", "--overwrite"], check=True)
            subprocess.run(["osmium", "add-locations-to-ways", f"sights-{c}.pbf", "-f", "opl,add_metadata=false",
                            "-o", os.path.join(work, f"sights-{c}.opl"), "--overwrite"], check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            print("Zajímavá místa se nepodařilo vybrat:", error)

def sight_kind(tags):
    if tags.get("historic") == "castle":
        return "chateau" if tags.get("castle_type") in ("palace", "stately", "manor", "chateau") else "castle"
    if tags.get("historic") == "ruins":
        return "ruins"
    if tags.get("tourism") == "viewpoint":
        return "viewpoint"
    if tags.get("mountain_pass") == "yes":
        return "pass"
    if tags.get("natural") == "waterfall":
        return "waterfall"
    if tags.get("natural") == "peak" and tags.get("ele"):
        return "peak"
    if tags.get("amenity") == "cafe":
        return "cafe"
    if tags.get("amenity") == "restaurant" and MOTOREST_RE.search(tags.get("name", "")):
        return "motorest"
    return None

def build_sights(work, out_path):
    tmp = out_path + ".tmp.json"
    build_points(sorted(glob.glob(os.path.join(work, "sights-*.opl"))), tmp,
                 lambda t: bool(t.get("name")) and sight_kind(t) is not None)
    with open(tmp, encoding="utf-8") as f:
        elements = json.load(f)["elements"]
    os.remove(tmp)
    sights = []
    for e in elements:
        lat = e["lat"] if "lat" in e else e["center"]["lat"]
        lon = e["lon"] if "lon" in e else e["center"]["lon"]
        sights.append([round(lat, 5), round(lon, 5), e["tags"]["name"], sight_kind(e["tags"])])
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"sights": sights, "license": "© OpenStreetMap contributors, ODbL 1.0"}, f, ensure_ascii=False, separators=(",", ":"))
    return len(sights)

# --- Catalogue of places for search (IKEA, Lidl, cafés, motorcycle services…), free and identical on iOS/Android ---
POI_FILTERS = ["nw/shop", "nw/amenity=cafe,restaurant,fast_food,pub,bar,fuel,motorcycle_parking,parking,pharmacy,hospital",
               "nw/tourism=hotel,motel,guest_house,hostel,camp_site,museum,attraction,viewpoint", "nw/historic=castle,ruins",
               # Obce a města: hledání cíle bez Mapboxu (okamžitě a i bez signálu).
               "n/place=city,town,village,hamlet,suburb"]

def extract_pois(work):
    for pbf in sorted(glob.glob("*.osm.pbf")):
        c = os.path.basename(pbf).split(".")[0]
        try:
            subprocess.run(["osmium", "tags-filter", pbf, *POI_FILTERS, "-o", f"pois-{c}.pbf", "--overwrite"], check=True)
            subprocess.run(["osmium", "add-locations-to-ways", f"pois-{c}.pbf", "-f", "opl,add_metadata=false",
                            "-o", os.path.join(work, f"pois-{c}.opl"), "--overwrite"], check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            print("Katalog míst se nepodařilo vybrat:", error)

def poi_kind(tags):
    shop, amenity, tourism, historic = tags.get("shop"), tags.get("amenity"), tags.get("tourism"), tags.get("historic")
    place = tags.get("place")
    if place in ("city", "town"): return "city"
    if place in ("village", "hamlet", "suburb"): return "village"
    if shop in ("motorcycle", "motorcycle_repair") or tags.get("service:vehicle:motorcycle") == "yes": return "moto"
    if shop in ("mall", "department_store"): return "mall"
    if shop in ("supermarket", "convenience"): return "supermarket"
    if shop: return "shop"
    if amenity == "cafe": return "cafe"
    if amenity == "restaurant": return "motorest" if MOTOREST_RE.search(tags.get("name", "")) else "restaurant"
    if amenity == "fast_food": return "fast_food"
    if amenity in ("pub", "bar"): return "pub"
    if amenity == "fuel": return "fuel"
    if amenity == "motorcycle_parking": return "parking_moto"
    if amenity == "parking": return "parking"
    if amenity == "pharmacy": return "pharmacy"
    if amenity == "hospital": return "hospital"
    if tourism in ("hotel", "motel", "guest_house", "hostel"): return "hotel"
    if tourism == "camp_site": return "camp"
    if tourism in ("museum", "attraction"): return "attraction"
    if tourism == "viewpoint": return "viewpoint"
    if historic in ("castle", "ruins"): return "castle"
    return None

def normalize(text):
    plain = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()

def write_bin(path, rows):
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)  # raw DEFLATE, same as road tiles
    with open(path, "wb") as f:
        f.write(compressor.compress(payload) + compressor.flush())

def build_pois(work, out_dir):
    """pois/n/<2 letters>.bin: places whose name has a word starting with those letters (name search);
    pois/t/<x>_<y>.bin: places in a road tile ("near me" chips). Row = [lat, lon, name, kind, town]."""
    tmp = os.path.join(out_dir, "pois.tmp.json")
    build_points(sorted(glob.glob(os.path.join(work, "pois-*.opl"))), tmp,
                 lambda t: poi_kind(t) is not None and (bool(t.get("name")) or t.get("amenity") == "motorcycle_parking")
                 and not (t.get("amenity") == "parking" and not t.get("name")))
    with open(tmp, encoding="utf-8") as f:
        elements = json.load(f)["elements"]
    os.remove(tmp)
    by_name, by_tile, count = defaultdict(list), defaultdict(list), 0
    for e in elements:
        lat = e["lat"] if "lat" in e else e["center"]["lat"]
        lon = e["lon"] if "lon" in e else e["center"]["lon"]
        tags = e["tags"]
        name = tags.get("name") or tags.get("brand") or "Parkování motorek"
        kind = poi_kind(tags)
        row = [round(lat, 5), round(lon, 5), name, kind, tags.get("addr:city") or tags.get("addr:place") or ""]
        keys = {w[:2] for w in normalize(name + " " + tags.get("brand", "")).split()[:5] if len(w) >= 2}
        for key in keys:
            by_name[key].append(row)
        by_tile[(math.floor(lon / TILE_LON), math.floor(lat / TILE_LAT))].append(row)
        count += 1
    os.makedirs(os.path.join(out_dir, "pois", "n"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "pois", "t"), exist_ok=True)
    for key, rows in by_name.items():
        write_bin(os.path.join(out_dir, "pois", "n", f"{key}.bin"), rows)
    for (x, y), rows in by_tile.items():
        write_bin(os.path.join(out_dir, "pois", "t", f"{x}_{y}.bin"), rows)
    return count

def main(work, site):
    out = os.path.join(site, "v1")
    os.makedirs(out, exist_ok=True)
    extract_urban(work)
    URBAN_CELLS.update(build_urban_cells(work))
    print("Zástavba: %d buněk" % len(URBAN_CELLS))
    extract_city_limits(work)
    signs = load_city_limits(work)
    print("Značky obcí: %d" % signs)
    roads, tiles = build_roads(sorted(glob.glob(os.path.join(work, "roads-*.opl"))), out)
    print("Limity: %s" % LIMIT_STATS)
    if LIMIT_STATS["none"] > 0.05 * max(1, sum(LIMIT_STATS.values())):
        print("::warning::Víc než 5 % úseků silnic nemá limit – zkontroluj zástavbu (urbanCells) a značky obcí.")
    cams = build_points(sorted(glob.glob(os.path.join(work, "cams-*.opl"))), os.path.join(out, "radars.json"),
                        lambda t: t.get("highway") == "speed_camera")
    fuel = build_points(sorted(glob.glob(os.path.join(work, "fuel-*.opl"))), os.path.join(out, "fuel.json"),
                        lambda t: t.get("amenity") == "fuel")
    extract_sights(work)
    # Not critical: without sights "Překvap mě" uses its built-in list, so a failure does not stop the deploy.
    sights = build_sights(work, os.path.join(out, "sights.json"))
    # Not critical either: without the catalogue the app searches addresses and Mapbox as before.
    try:
        extract_pois(work)
        pois = build_pois(work, out)
    except Exception as error:
        print("Katalog míst selhal:", error)
        pois = 0
    print("Katalog míst: %d" % pois)
    meta = {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "roads": roads, "tiles": tiles,
            "speedCameras": cams, "fuelStations": fuel, "sights": sights, "urbanCells": len(URBAN_CELLS), "citySigns": signs, "pois": pois,
            "limits": dict(LIMIT_STATS, noneShare=round(LIMIT_STATS["none"] / max(1, sum(LIMIT_STATS.values())), 4)), "license": "© OpenStreetMap contributors, ODbL 1.0"}
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
