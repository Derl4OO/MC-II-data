"""Test of our Valhalla route server with the apps' own rules: Rychlá, Normální (three settings) and Zábavná
exactly as the apps choose it (alternatives + 8 detours beside the straight line, our bend count,
at most half the roads shared with Normální, no loops, at most 1.7x the fastest time). A second Zábavná tries a
lower top speed for Valhalla, so fast straight roads lose their advantage and the route differs more from Rychlá.

Destinations given by name ("to_place") are looked up in our own catalogue of towns and villages (MC-II-data).
Writes report.json, routes.geojson and index.html (map with a route picker + table). Mapbox results are never
stored here (Mapbox terms). Only the standard library is used."""
import json, math, os, sys, time, unicodedata, re, urllib.request, zlib

SERVER = os.environ.get("VALHALLA", "http://localhost:8002")
CATALOGUE = "https://derl4oo.github.io/MC-II-data/v1/pois/n/"
LABELS = {
    "fast": "Rychlá", "normal": "Normální 0,0", "normal_02": "Normální 0,2", "normal_04": "Normální 0,4",
    "fun": "Zábavná (jako aplikace)", "fun_slow": "Zábavná, max. 80 km/h",
}
COLORS = {"fast": "#1f6fe5", "normal": "#888888", "normal_02": "#a0a0a0", "normal_04": "#c8c8c8",
          "fun": "#e8590c", "fun_slow": "#2b8a3e"}

# --- geometry (the same as the apps: RouteFunScore, MotoCurveDetector, hasLoop, sharedShare) -------------------
def decode(polyline, precision=6):
    coords, index, lat, lon, factor = [], 0, 0, 0, 10 ** precision
    while index < len(polyline):
        for which in (0, 1):
            shift = result = 0
            while True:
                b = ord(polyline[index]) - 63; index += 1
                result |= (b & 0x1F) << shift; shift += 5
                if b < 0x20: break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if which == 0: lat += delta
            else: lon += delta
        coords.append((lat / factor, lon / factor))
    return coords

def dist(a, b):
    r = 6371000.0
    dlat = math.radians(b[0] - a[0]); dlon = math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(min(1, math.sqrt(h)))

def resample(path, spacing=20.0):
    if not path: return []
    out, carried = [path[0]], 0.0
    for a, b in zip(path, path[1:]):
        seg = dist(a, b)
        if seg <= 0: continue
        pos = spacing - carried
        while pos <= seg:
            t = pos / seg
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)); pos += spacing
        carried = seg - (pos - spacing)
    return out

def circumradius(a, b, c):
    ab, bc, ac = dist(a, b), dist(b, c), dist(a, c)
    s = (ab + bc + ac) / 2
    area2 = s * (s - ab) * (s - bc) * (s - ac)
    return float("inf") if area2 <= 1 else (ab * bc * ac) / (4 * math.sqrt(area2))

def count_bends(path):
    samples = resample(path)
    if len(samples) < 5: return 0, 0
    bends = sharp = 0; in_bend = False; tightest = float("inf")
    for i in range(2, len(samples) - 2):
        radius = circumradius(samples[i - 2], samples[i], samples[i + 2])
        if radius < 150:
            in_bend = True; tightest = min(tightest, radius)
        elif in_bend:
            bends += 1; sharp += tightest < 60; in_bend = False; tightest = float("inf")
    if in_bend: bends += 1; sharp += tightest < 60
    return bends, sharp

def fun_score(path, distance_m, junctions):
    km = max(distance_m / 1000, 0.1)
    bends, sharp = count_bends(path)
    raw = bends / km * 25 + (sharp / bends if bends else 0) * 20 - max(junctions / km - 1, 0) * 8
    return bends, sharp, round(min(max(raw, 0), 100))

def has_loop(path):
    m_lat = 110540.0; m_lon = math.cos(math.radians(path[0][0])) * 111320
    cells, along, prev = {}, 0.0, None
    for p in path:
        x, y = p[1] * m_lon, p[0] * m_lat
        samples = []
        if prev is None: samples.append((x, y, 0.0))
        else:
            d = math.hypot(x - prev[0], y - prev[1]); steps = max(1, int(d / 10))
            for k in range(1, steps + 1):
                t = k / steps; samples.append((prev[0] + (x - prev[0]) * t, prev[1] + (y - prev[1]) * t, along + d * t))
            along += d
        prev = (x, y)
        for q in samples:
            cx, cy = math.floor(q[0] / 25), math.floor(q[1] / 25)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for o in cells.get((cx + dx, cy + dy), ()):
                        if q[2] - o[2] > 300 and math.hypot(o[0] - q[0], o[1] - q[1]) < 25: return True
            cells.setdefault((cx, cy), []).append(q)
    return False

def without_ends(path, meters=1500.0):
    first, last = path[0], path[-1]
    middle = [p for p in path if dist(p, first) > meters and dist(p, last) > meters]
    return middle if len(middle) >= 10 else path

def shared_share(path, other):
    def sample(points, n):
        return points if len(points) <= n else [points[i * (len(points) - 1) // (n - 1)] for i in range(n)]
    probes, ref = sample(path, 150), sample(other, 1200)
    m_lon = math.cos(math.radians(probes[0][0])) * 111320
    near = sum(1 for q in probes if any(((p[1] - q[1]) * m_lon) ** 2 + ((p[0] - q[0]) * 110540) ** 2 < 3600 for p in ref))
    return near / len(probes)

def detour_points(origin, destination):
    mid = (origin[0] + destination[0]) / 2
    per_lat, per_lon = 110540.0, math.cos(math.radians(mid)) * 111320
    dx = (destination[1] - origin[1]) * per_lon; dy = (destination[0] - origin[0]) * per_lat
    length = math.hypot(dx, dy)
    if length <= 3000: return []
    px, py = -dy / length, dx / length
    width = max(length, 20000.0)  # short trips get detours as wide as a 20 km trip (0.6.55 / 0.3.61)
    places = [(0.5, 0.15), (0.5, -0.15), (0.5, 0.3), (0.5, -0.3), (0.33, 0.2), (0.33, -0.2), (0.67, 0.2), (0.67, -0.2)]
    out = []
    for along, side in places:
        base_lat = origin[0] + (destination[0] - origin[0]) * along
        base_lon = origin[1] + (destination[1] - origin[1]) * along
        out.append((base_lat + py * width * side / per_lat, base_lon + px * width * side / per_lon))
    return out

# --- requests ---------------------------------------------------------------------------------------------
def request(points, costing, alternates=0):
    locations = [{"lat": p[0], "lon": p[1], "type": "break" if i in (0, len(points) - 1) else "through"} for i, p in enumerate(points)]
    body = {"locations": locations, "costing": "motorcycle",
            "costing_options": {"motorcycle": dict(costing, use_trails=0.0, exclude_unpaved=True)},
            "alternates": alternates, "format": "osrm", "shape_format": "polyline6", "banner_instructions": True,
            "language": "cs-CZ", "units": "kilometers"}
    req = urllib.request.Request(SERVER + "/route", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as response:
        answer = json.load(response)
    return [describe(r) for r in answer.get("routes", [])]

def describe(r):
    coords = decode(r["geometry"])
    legs = r.get("legs", [])
    junctions = sum(len(s.get("intersections", [])) for l in legs for s in l.get("steps", []))
    roads = {}
    for leg in legs:
        for step in leg.get("steps", []):
            key = step.get("ref") or step.get("name") or "?"
            roads[key] = roads.get(key, 0) + step.get("distance", 0)
    bends, sharp, score = fun_score(coords, r["distance"], junctions)
    return {"coords": coords, "distance": r["distance"], "duration": r["duration"], "bends": bends, "sharp": sharp, "score": score,
            "roads": [f"{k} {round(v / 1000)} km" for k, v in sorted(roads.items(), key=lambda kv: -kv[1])[:5]]}

def safe(fn, *args):
    try: return fn(*args)
    except Exception as error:  # noqa: BLE001
        print("  chyba:", str(error)[:120]); return []

def choose_fun(base, detours, normal, fast_time):
    """The apps' rule (RoutePlanner.chooseFunRoute)."""
    limit = max(fast_time * 1.7, fast_time + 600)
    required = max(normal["bends"] + 3, math.ceil(normal["bends"] * 1.2))
    best, best_rank = None, -1e9
    for c in base + detours:
        if c["duration"] > limit or c["bends"] < required: continue
        if shared_share(without_ends(c["coords"]), normal["coords"]) > 0.5: continue
        if has_loop(c["coords"]): continue
        rank = c["bends"] + c["sharp"] + c["score"] * 0.3 - max(0, c["duration"] - fast_time) / 60 * 0.3
        if rank > best_rank: best, best_rank = c, rank
    return best

# --- our catalogue of towns and villages --------------------------------------------------------------------
_catalogue = {}
def normalize(text):
    plain = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()

def place(name, near):
    key = normalize(name)[:2]
    if key not in _catalogue:
        try:
            with urllib.request.urlopen(CATALOGUE + key + ".bin", timeout=60) as response:
                _catalogue[key] = json.loads(zlib.decompress(response.read(), -15))
        except Exception as error:  # noqa: BLE001
            print("katalog", key, error); _catalogue[key] = []
    rows = [r for r in _catalogue[key] if normalize(r[2]) == normalize(name) and r[3] in ("village", "city")]
    if not rows: return None
    best = min(rows, key=lambda r: dist((r[0], r[1]), near))
    return (best[0], best[1]) if dist((best[0], best[1]), near) < 30000 else None

# --- report -------------------------------------------------------------------------------------------------
def summary(c):
    return None if c is None else {"distance_km": round(c["distance"] / 1000, 1), "duration_min": round(c["duration"] / 60),
                                   "bends": c["bends"], "sharp": c["sharp"], "score": c["score"],
                                   "avg_kmh": round(c["distance"] / max(c["duration"], 1) * 3.6), "roads": c["roads"]}

def write_page(rows, features, kinds, out):
    """Map with a route picker and the table; routes are inside the page (works opened from a file)."""
    geo = json.dumps({"type": "FeatureCollection", "features": [
        dict(f, geometry=dict(f["geometry"], coordinates=[[round(x, 5), round(y, 5)] for x, y in f["geometry"]["coordinates"][::3]]))
        for f in features]}, separators=(",", ":"))
    def cell(i):
        if not i: return "<i>není – stejná jako Normální</i>"
        if "error" in i: return "—"
        return (f"{i['distance_km']} km · {i['duration_min']} min · {i['bends']} zatáček ({i['sharp']} ostrých), "
                f"⌀ {i['avg_kmh']} km/h<br><small>{', '.join(i.get('roads', []))}</small>")
    head = "".join(f"<th style='border-bottom:4px solid {COLORS.get(k, '#000')}'>{LABELS.get(k, k)}</th>" for k in kinds)
    table = "".join(f"<tr data-name=\"{r['name']}\" style=\"cursor:pointer\"><td>{r['name']}</td>"
                    + "".join(f"<td>{cell(r.get(k))}</td>" for k in kinds) + "</tr>" for r in rows)
    checks = "".join(f"<label style='margin-right:10px'><input type=checkbox data-kind='{k}' checked> "
                     f"<span style='color:{COLORS.get(k, '#000')}'>■</span> {LABELS.get(k, k)}</label>" for k in kinds)
    html = f"""<!doctype html><meta charset=utf-8><title>MotoCesta – test Valhally</title>
<link rel=stylesheet href=https://unpkg.com/leaflet@1.9.4/dist/leaflet.css><script src=https://unpkg.com/leaflet@1.9.4/dist/leaflet.js></script>
<style>body{{font:14px -apple-system,Arial;margin:16px}}#map{{height:560px}}table{{border-collapse:collapse;margin-top:12px}}td,th{{border:1px solid #ddd;padding:4px 8px;vertical-align:top}}</style>
<h1>Test Valhally – motorkářský profil</h1><p>Mapa © přispěvatelé OpenStreetMap.</p>
<p><label>Trasa: <select id=pick></select></label> nebo klikni na řádek tabulky.</p><p>{checks}</p><div id=map></div>
<table><tr><th>Trasa</th>{head}</tr>{table}</table>
<script>const m=L.map('map').setView([49.4,17.5],7);L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{attribution:'© OpenStreetMap'}}).addTo(m);
const g={geo};const colors={json.dumps(COLORS)};const labels={json.dumps(LABELS, ensure_ascii=False)};
const names=[...new Set(g.features.map(f=>f.properties.name))];const sel=document.getElementById('pick');
sel.innerHTML='<option value="">Všechny trasy</option>'+names.map(n=>`<option>${{n}}</option>`).join('');
let layer=null,current='';const on=k=>document.querySelector(`input[data-kind="${{k}}"]`)?.checked!==false;
function show(name,fit=true){{current=name;if(layer)m.removeLayer(layer);const fs=g.features.filter(f=>(!name||f.properties.name===name)&&on(f.properties.kind));
layer=L.geoJSON({{type:'FeatureCollection',features:fs}},{{style:f=>({{color:colors[f.properties.kind]||'#000',weight:name?5:3,opacity:0.85}})}}).bindPopup(l=>l.feature.properties.name+' · '+(labels[l.feature.properties.kind]||l.feature.properties.kind)).addTo(m);
if(fit&&fs.length)m.fitBounds(layer.getBounds(),{{padding:[20,20]}});sel.value=name;document.querySelectorAll('tr[data-name]').forEach(r=>r.style.background=r.dataset.name===name?'#fff3bf':'');}}
sel.onchange=()=>show(sel.value);document.querySelectorAll('input[data-kind]').forEach(c=>c.onchange=()=>show(current,false));
document.querySelectorAll('tr[data-name]').forEach(r=>r.onclick=()=>{{show(r.dataset.name);window.scrollTo(0,0);}});show('');</script>"""
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(html)

def main(out):
    os.makedirs(out, exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    tests = json.load(open(os.path.join(here, "test_routes.json"), encoding="utf-8"))
    kinds = ["fast", "normal", "normal_02", "normal_04", "fun", "fun_slow"]
    rows, features, failures = [], [], 0
    for t in tests:
        frm, to = tuple(t["from"]), tuple(t["to"])
        if t.get("to_place"):
            found = place(t["to_place"], to)
            if found: to = found
            else: print("  cíl nenalezen v katalogu:", t["to_place"])
        print(t["name"])
        row = {"name": t["name"], "to": to}
        got = {}
        got["fast"] = (safe(request, [frm, to], {"use_highways": 1.0, "use_tolls": 0.5}) or [None])[0]
        got["normal"] = (safe(request, [frm, to], {"use_highways": 0.0, "use_tolls": 0.0}) or [None])[0]
        got["normal_02"] = (safe(request, [frm, to], {"use_highways": 0.2, "use_tolls": 0.0}) or [None])[0]
        got["normal_04"] = (safe(request, [frm, to], {"use_highways": 0.4, "use_tolls": 0.0}) or [None])[0]
        fast, normal = got["fast"], got["normal"]
        if fast and normal:
            vias = detour_points(frm, to)
            for kind, extra in (("fun", {}), ("fun_slow", {"top_speed": 80})):
                costing = dict({"use_highways": 0.0, "use_tolls": 0.5}, **extra)
                base = safe(request, [frm, to], costing, 2)
                detours = [c for via in vias for c in safe(request, [frm, via, to], costing)]
                got[kind] = choose_fun(base, detours, normal, fast["duration"])
        for kind in kinds:
            c = got.get(kind)
            if kind in ("fast", "normal") and c is None: failures += 1
            row[kind] = summary(c)
            if c: features.append({"type": "Feature", "properties": {"name": t["name"], "kind": kind},
                                   "geometry": {"type": "LineString", "coordinates": [[p[1], p[0]] for p in c["coords"]]}})
        rows.append(row)
    json.dump({"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "routes": rows},
              open(os.path.join(out, "report.json"), "w"), ensure_ascii=False, indent=1)
    json.dump({"type": "FeatureCollection", "features": features}, open(os.path.join(out, "routes.geojson"), "w"))
    write_page(rows, features, kinds, out)
    print(f"Hotovo: {len(rows)} tras, {failures} chyb")
    if failures > len(rows) // 3:
        sys.exit("Příliš mnoho chyb – server tras nefunguje správně.")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "valhalla-report")
