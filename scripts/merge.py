#!/usr/bin/env python3
"""Joins the per-country builds (region.py) into the published site (Tools/data.yml, job "site").

    python3 scripts/merge.py <parts> <work> <site>

<parts>/<cc>/ are the countries. Output <site>/v1/ keeps the paths the apps already use:
  roads/…               countries with verified limits (tiles on a border are joined)
  radars.json, fuel.json, sights.json   CZ + SK as before (the apps download these whole)
  <kind>/<cc>.json      the same per country, for the apps' coming update (abroad)
  pois/n/…              name search CZ + SK as before; pois/n/<cc>/… per country for search abroad
  pois/t/…              places by tile, all countries ("near me" works everywhere)
  moto/{z}/{x}/{y}.pbf  map layer: curvy roads and our places, all countries
  style/, config.json, closures/, addr/ (CZ, RÚIAN), meta.json with stats per country
"""
import glob
import gzip
import json
import os
import shutil
import sys
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build  # noqa: E402
import moto_tiles  # noqa: E402

HOME = ("cz", "sk")  # what today's apps download as whole files


def inflate(path):
    with open(path, "rb") as f:
        return json.loads(zlib.decompress(f.read(), -15))


def merge_roads(parts, out):
    folder = os.path.join(out, "roads")
    os.makedirs(folder, exist_ok=True)
    count = 0
    for path in glob.glob(os.path.join(parts, "*", "roads", "*.bin")):
        target = os.path.join(folder, os.path.basename(path))
        if os.path.exists(target):
            roads = {r["id"]: r for r in inflate(target)}
            roads.update({r["id"]: r for r in inflate(path)})
            build.write_bin(target, list(roads.values()))
        else:
            shutil.copy(path, target)
            count += 1
    return len(os.listdir(folder))


def folder_size(folder):
    return sum(os.path.getsize(p) for p in glob.glob(os.path.join(folder, "**"), recursive=True) if os.path.isfile(p))


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def report_problems(stats, countries, size):
    """problems.md in the current folder when something needs a look; the workflow then opens a GitHub issue
    (GitHub e-mails the repository owner). Julien 3. 11.: a drop in the data must reach us."""
    here = os.path.dirname(os.path.abspath(__file__))
    wanted = [c["id"] for c in read_json(os.path.join(here, "..", "config", "countries.json"), {"countries": []})["countries"]]
    lines = []
    for cc in wanted:
        if cc not in countries:
            lines.append(f"- **{cc}**: sestavení země selhalo a minulá verze nebyla – země v datech chybí.")
        elif stats.get(cc, {}).get("kept"):
            lines.append(f"- **{cc}**: data vypadala špatně ({'; '.join(stats[cc].get('problems', []))}), zůstává minulá verze.")
    if size > 900e6:
        lines.append(f"- Data mají {round(size / 1e6)} MB, limit GitHub Pages je 1 GB – přejít na Cloudflare R2.")
    if lines:
        with open("problems.md", "w", encoding="utf-8") as f:
            f.write("Kontrola dat MotoCesty našla problém (" + time.strftime("%d. %m. %Y") + "):\n\n" + "\n".join(lines)
                    + "\n\nPodrobnosti jsou v logu workflow a ve v1/meta.json. Napiš to Claudovi, opraví to.\n")
        print("::warning::" + " | ".join(lines))


def main(parts, work, site):
    out = os.path.join(site, "v1")
    os.makedirs(out, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    countries = sorted(os.path.basename(p) for p in glob.glob(os.path.join(parts, "*")) if os.path.isdir(p))
    stats = {cc: read_json(os.path.join(parts, cc, "stats.json"), {}) for cc in countries}
    print("Země:", ", ".join(countries))

    road_tiles = merge_roads(parts, out)
    # Whole-file data: CZ + SK as today, every country also on its own.
    for name, key in (("radars", "elements"), ("fuel", "elements"), ("sights", "sights")):
        os.makedirs(os.path.join(out, name), exist_ok=True)
        home = []
        for cc in countries:
            data = read_json(os.path.join(parts, cc, f"{name}.json"), {key: []})
            with open(os.path.join(out, name, f"{cc}.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            if cc in HOME:
                home += data.get(key, [])
        result = {key: home}
        if name == "sights":
            result["license"] = "© OpenStreetMap contributors, ODbL 1.0"
        with open(os.path.join(out, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

    # Places: tiles for everyone, name search CZ + SK as today and per country.
    all_rows, home_rows = [], []
    for cc in countries:
        path = os.path.join(parts, cc, "pois.json.gz")
        if not os.path.exists(path):
            continue
        with gzip.open(path, "rt", encoding="utf-8") as f:
            rows = json.load(f)
        build.write_pois(rows, out, name_dir=("pois", "n", cc), tiles=False)
        all_rows += rows
        if cc in HOME:
            home_rows += rows
    build.write_pois(home_rows, out, tiles=False)
    build.write_pois(all_rows, out, name_dir=None, tiles=True)

    # Map layer: curves + our places of all countries.
    runs, places = [], []
    for cc in countries:
        path = os.path.join(parts, cc, "curves.json.gz")
        if os.path.exists(path):
            with gzip.open(path, "rt") as f:
                runs += [(level, [tuple(p) for p in coords]) for level, coords in json.load(f)]
        for lat, lon, name, kind in read_json(os.path.join(parts, cc, "sights.json"), {"sights": []})["sights"]:
            if kind in moto_tiles.PLACES:
                places.append((lon, lat, name, moto_tiles.PLACES[kind]))
    tiles = moto_tiles.build_tiles(runs, places, out)
    print("Vrstva mapy: %d úseků zatáček, %d míst, %d dlaždic" % (len(runs), len(places), tiles))

    # The rest as in build.py (not critical).
    here = os.path.dirname(os.path.abspath(__file__))
    for label, action in (
        ("config.json", lambda: shutil.copy(os.path.join(here, "..", "config", "app.json"), os.path.join(out, "config.json"))),
        ("styl mapy", lambda: __import__("map_style").main(out)),
        ("uzavírky", lambda: __import__("closures").main(out)),
    ):
        try:
            action()
        except Exception as error:  # noqa: BLE001
            print(f"::warning::{label} selhal:", error)
    addresses = 0
    try:
        import ruian
        addresses, _, _ = ruian.build_addresses(work, out)
    except Exception as error:  # noqa: BLE001
        print("::warning::Adresy RÚIAN selhaly:", error)

    size = folder_size(site)
    # GitHub Pages takes at most 1 GB: until the data move to Cloudflare R2, the extras for abroad that
    # today's apps do not use yet go first (name search and whole files per foreign country).
    if size > 950e6:
        for cc in countries:
            if cc in HOME:
                continue
            shutil.rmtree(os.path.join(out, "pois", "n", cc), ignore_errors=True)
            for name in ("radars", "fuel", "sights"):
                path = os.path.join(out, name, f"{cc}.json")
                if os.path.exists(path):
                    os.remove(path)
        print("::warning::Data přes 950 MB (%d MB) – vynecháno hledání a soubory pro zahraničí, mapa zůstává. Přejít na R2." % (size / 1e6))
        size = folder_size(site)
    meta = {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "countries": stats,
            "roadTiles": road_tiles, "mapLayerTiles": tiles, "addresses": addresses, "sizeMB": round(size / 1e6),
            "license": "© OpenStreetMap contributors, ODbL 1.0", "addressLicense": "RÚIAN © ČÚZK, CC BY 4.0"}
    # Kept for today's apps (they read these keys).
    home = [stats.get(cc, {}) for cc in HOME]
    meta.update({"roads": sum(s.get("roads", 0) for s in home), "speedCameras": sum(s.get("cams", 0) for s in home),
                 "fuelStations": sum(s.get("fuel", 0) for s in home), "sights": sum(s.get("sights", 0) for s in home),
                 "pois": sum(s.get("pois", 0) for s in home)})
    with open(os.path.join(out, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    with open(os.path.join(site, "index.html"), "w", encoding="utf-8") as f:
        f.write("<!doctype html><meta charset=utf-8><title>MotoCesta data</title><h1>MotoCesta data</h1>"
                "<p>Data © <a href='https://www.openstreetmap.org/copyright'>přispěvatelé OpenStreetMap</a>, ODbL.</p>"
                f"<pre>{json.dumps(meta, indent=1, ensure_ascii=False)}</pre>")
    print(json.dumps(meta, indent=1, ensure_ascii=False))
    report_problems(stats, countries, size)
    if size > 900e6:
        print("::warning::Data mají %d MB – blíží se limit GitHub Pages (1 GB). Je čas přejít na Cloudflare R2." % (size / 1e6))
    if meta["roads"] == 0 or meta["speedCameras"] == 0 or meta["fuelStations"] == 0:
        sys.exit("Data pro Česko a Slovensko chybí – nasazení zastaveno.")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
