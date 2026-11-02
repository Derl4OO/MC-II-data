"""Road closures and roadworks from official open sources, in one simple format for the apps:
closures/<country>.json = {"generatedAt", "source", "items": [{"id","lat","lon","kind","title","from","until"}]}.
Germany: Autobahn API (Autobahn GmbH, motorways). France and Czechia (NDIC) follow once access and terms are checked.
Only the standard library. Run: python3 scripts/closures.py <out dir>"""
import json, os, sys, time, urllib.request

def get(url):
    request = urllib.request.Request(url, headers={"User-Agent": "MotoCesta-data (github.com/Derl4OO/MC-II-data)"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)

def germany():
    base = "https://verkehr.autobahn.de/o/autobahn"
    items = []
    for road in get(base).get("roads", []):
        road = road.strip()
        for service, kind in (("closure", "closure"), ("roadworks", "roadworks")):
            try:
                answer = get(f"{base}/{urllib.request.quote(road)}/services/{service}")
            except Exception as error:  # noqa: BLE001
                print("DE", road, service, error); continue
            for entry in answer.get(service, []):
                c = entry.get("coordinate") or {}
                try:
                    lat, lon = float(c.get("lat")), float(c.get("long"))
                except (TypeError, ValueError):
                    continue
                items.append({"id": entry.get("identifier"), "lat": round(lat, 5), "lon": round(lon, 5),
                              "kind": "closure" if entry.get("isBlocked") in (True, "true") or kind == "closure" else "roadworks",
                              "title": f"{road}: {entry.get('title', '')}".strip(),
                              "from": entry.get("startTimestamp"), "until": None})
        time.sleep(0.2)
    return {"source": "Autobahn GmbH des Bundes (verkehr.autobahn.de)", "items": items}

def main(out):
    os.makedirs(os.path.join(out, "closures"), exist_ok=True)
    for country, build in (("de", germany),):
        try:
            data = build()
        except Exception as error:  # noqa: BLE001
            print("::warning::Uzavírky", country, "selhaly:", error); continue
        data["generatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        json.dump(data, open(os.path.join(out, "closures", f"{country}.json"), "w"), ensure_ascii=False, separators=(",", ":"))
        print(country, len(data["items"]), "položek")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "site/v1")
