"""Test of our Valhalla route server: the same requests as the apps (Rychlá, Normální, Zábavná base) for the
routes in test_routes.json. Writes report.json, routes.geojson and index.html (map + table) to the output folder.
Only the standard library is used. Mapbox results are never stored here (Mapbox terms)."""
import json, math, os, sys, time, urllib.request

SERVER = os.environ.get("VALHALLA", "http://localhost:8002")
KINDS = {
    "fast": {"use_highways": 1.0, "use_tolls": 0.5},
    # Normální: hledáme nastavení, které nejede po dálnici, ale ani zbytečně po vesnicích (2. test).
    "normal": {"use_highways": 0.0, "use_tolls": 0.0},
    "normal_02": {"use_highways": 0.2, "use_tolls": 0.0},
    "normal_04": {"use_highways": 0.4, "use_tolls": 0.0},
}

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
    dy = (b[0] - a[0]) * 110540; dx = (b[1] - a[1]) * 111320 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)

def bends(coords):
    """Bends = heading changes of at least 30 degrees within about 100 m (the same idea as the apps' fun score)."""
    pts, acc = [coords[0]], 0.0
    for p in coords[1:]:
        acc += dist(pts[-1], p)
        if dist(pts[-1], p) >= 25: pts.append(p)
    def heading(a, b):
        return math.degrees(math.atan2((b[1] - a[1]) * math.cos(math.radians(a[0])), b[0] - a[0]))
    count, sharp, i = 0, 0, 1
    while i < len(pts) - 2:
        h1 = heading(pts[i - 1], pts[i]); h2 = heading(pts[i + 2], pts[min(i + 3, len(pts) - 1)]) if i + 3 < len(pts) else heading(pts[i + 1], pts[i + 2])
        d = abs((h2 - h1 + 180) % 360 - 180)
        if d >= 30:
            count += 1
            if d >= 70: sharp += 1
            i += 3
        else:
            i += 1
    return count, sharp

def route(frm, to, kind):
    body = {"locations": [{"lat": frm[0], "lon": frm[1], "type": "break"}, {"lat": to[0], "lon": to[1], "type": "break"}],
            "costing": "motorcycle",
            "costing_options": {"motorcycle": dict(KINDS[kind], use_trails=0.0, exclude_unpaved=True)},
            "alternates": 0, "format": "osrm", "shape_format": "polyline6", "banner_instructions": True,
            "language": "cs-CZ", "units": "kilometers"}
    request = urllib.request.Request(SERVER + "/route", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    started = time.time()
    with urllib.request.urlopen(request, timeout=60) as response:
        answer = json.load(response)
    took = time.time() - started
    r = answer["routes"][0]
    coords = decode(r["geometry"])
    legs = r.get("legs", [])
    steps = sum(len(l.get("steps", [])) for l in legs)
    has_segment_times = any("annotation" in l for l in legs)
    b, s = bends(coords)
    # Silnice podle délky (ref nebo název), aby šlo poznat, kudy trasa vede.
    roads = {}
    for leg in legs:
        for step in leg.get("steps", []):
            key = step.get("ref") or step.get("name") or "?"
            roads[key] = roads.get(key, 0) + step.get("distance", 0)
    top = [f"{k} {round(v / 1000)} km" for k, v in sorted(roads.items(), key=lambda kv: -kv[1])[:5]]
    return {"distance_km": round(r["distance"] / 1000, 1), "duration_min": round(r["duration"] / 60), "bends": b, "sharp": s,
            "avg_kmh": round(r["distance"] / max(r["duration"], 1) * 3.6), "roads": top,
            "steps": steps, "segment_times": has_segment_times, "ms": round(took * 1000)}, coords

def main(out):
    os.makedirs(out, exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    tests = json.load(open(os.path.join(here, "test_routes.json"), encoding="utf-8"))
    rows, features, failures = [], [], 0
    for t in tests:
        row = {"name": t["name"]}
        for kind in KINDS:
            try:
                info, coords = route(t["from"], t["to"], kind)
                row[kind] = info
                features.append({"type": "Feature", "properties": {"name": t["name"], "kind": kind},
                                 "geometry": {"type": "LineString", "coordinates": [[c[1], c[0]] for c in coords]}})
            except Exception as error:  # noqa: BLE001
                row[kind] = {"error": str(error)[:200]}; failures += 1
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))
    json.dump({"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "routes": rows}, open(os.path.join(out, "report.json"), "w"), ensure_ascii=False, indent=1)
    json.dump({"type": "FeatureCollection", "features": features}, open(os.path.join(out, "routes.geojson"), "w"))
    def cell(i):
        return "—" if "error" in i else f"{i['distance_km']} km · {i['duration_min']} min · {i['bends']} zatáček, ⌀ {i['avg_kmh']} km/h<br><small>{', '.join(i['roads'])}</small>"
    table = "".join(f"<tr><td>{r['name']}</td>" + "".join(f"<td>{cell(r[k])}</td>" for k in KINDS) + "</tr>" for r in rows)
    # Trasy přímo ve stránce: otevřená ze souboru (dvojklikem) by si vedlejší soubor načíst nesměla.
    geo = json.dumps({"type": "FeatureCollection", "features": [
        dict(f, geometry=dict(f["geometry"], coordinates=[[round(x, 5), round(y, 5)] for x, y in f["geometry"]["coordinates"][::3]]))
        for f in features]}, separators=(",", ":"))
    html = f"""<!doctype html><meta charset=utf-8><title>MotoCesta – test Valhally</title>
<link rel=stylesheet href=https://unpkg.com/leaflet@1.9.4/dist/leaflet.css><script src=https://unpkg.com/leaflet@1.9.4/dist/leaflet.js></script>
<style>body{{font:14px -apple-system,Arial;margin:16px}}#map{{height:520px}}table{{border-collapse:collapse;margin-top:12px}}td,th{{border:1px solid #ddd;padding:4px 8px}}</style>
<h1>Test Valhally – motorkářský profil</h1><p>Rychlá modře, Normální 0,0 šedě, 0,2 oranžově, 0,4 zeleně. Mapa © přispěvatelé OpenStreetMap.</p><div id=map></div>
<table><tr><th>Trasa</th><th>Rychlá</th><th>Normální 0,0</th><th>Normální 0,2</th><th>Normální 0,4</th></tr>{table}</table>
<script>const m=L.map('map').setView([49.4,17.5],7);L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{attribution:'© OpenStreetMap'}}).addTo(m);
const g={geo};L.geoJSON(g,{{style:f=>({{color:{{fast:'#1f6fe5',normal:'#888',normal_02:'#e8590c',normal_04:'#2b8a3e'}}[f.properties.kind],weight:3}})}}).bindPopup(l=>l.feature.properties.name+' · '+l.feature.properties.kind).addTo(m);</script>"""
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(html)
    print(f"Hotovo: {len(rows)} tras, {failures} chyb")
    if failures > len(rows):  # more than a third of requests failed
        sys.exit("Příliš mnoho chyb – server tras nefunguje správně.")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "valhalla-report")
