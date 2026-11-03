#!/usr/bin/env python3
"""One country of the MotoCesta data build (run in parallel, one job per country, see Tools/data.yml).

    python3 scripts/region.py <cc> <work> <out> [<previous>]

Expects <cc>.osm.pbf (Geofabrik) in the current folder. Writes into <out>:
  roads/<x>_<y>.bin   speed limits and road network – for countries with legal rules in config/limits.json
                      ("limits": true in config/countries.json)
  radars.json, fuel.json, sights.json   as in build.py, for this country
  pois.json.gz        places for search ([lat, lon, name, kind, town, brand])
  curves.json.gz      curvy road stretches ([level, [[lon, lat], …]]) for the map layer (moto_tiles.py)
  stats.json          counts, compared with the previous accepted build of the country
  ACCEPTED            only when the counts look sane; otherwise the previous build is kept (copied to <out>)
Data © OpenStreetMap contributors, ODbL.
"""
import gzip
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build  # noqa: E402
import moto_tiles  # noqa: E402

CHECKED = ("pois", "sights", "fuel", "curvesKm", "roads")
DROP = 0.6  # a count below 60 % of the previous build means broken input data


def country(cc):
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "..", "config", "countries.json"), encoding="utf-8") as f:
        return next(c for c in json.load(f)["countries"] if c["id"] == cc)


def osmium(pbf, filters, opl, locations=True):
    if locations:
        subprocess.run(["osmium", "tags-filter", pbf, *filters, "-o", opl + ".pbf", "--overwrite"], check=True)
        subprocess.run(["osmium", "add-locations-to-ways", opl + ".pbf", "-f", "opl,add_metadata=false", "-o", opl, "--overwrite"], check=True)
        os.remove(opl + ".pbf")
    else:
        subprocess.run(["osmium", "tags-filter", pbf, *filters, "-f", "opl,add_metadata=false", "-o", opl, "--overwrite"], check=True)


def run(cc, work, out):
    info = country(cc)
    pbf = f"{cc}.osm.pbf"
    os.makedirs(work, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    stats = {"country": cc}
    if info.get("limits"):
        kinds = "w/highway=motorway,motorway_link,trunk,trunk_link,primary,primary_link,secondary,secondary_link,tertiary,tertiary_link,unclassified,residential,living_street"
    else:
        kinds = "w/highway=trunk,primary,secondary,tertiary,unclassified"  # only for the curves layer
    osmium(pbf, [kinds], os.path.join(work, f"roads-{cc}.opl"))
    osmium(pbf, ["n/highway=speed_camera"], os.path.join(work, f"cams-{cc}.opl"), locations=False)
    osmium(pbf, ["nw/amenity=fuel"], os.path.join(work, f"fuel-{cc}.opl"))
    if info.get("limits"):
        build.set_country(cc)  # legal default limits of this country (config/limits.json)
        build.extract_urban(work)
        build.URBAN_CELLS.update(build.build_urban_cells(work))
        build.extract_city_limits(work)
        build.load_city_limits(work)
        stats["roads"], _ = build.build_roads([os.path.join(work, f"roads-{cc}.opl")], out)
        stats["limits"] = dict(build.LIMIT_STATS)
    stats["cams"] = build.build_points([os.path.join(work, f"cams-{cc}.opl")], os.path.join(out, "radars.json"),
                                       lambda t: t.get("highway") == "speed_camera")
    stats["fuel"] = build.build_points([os.path.join(work, f"fuel-{cc}.opl")], os.path.join(out, "fuel.json"),
                                       lambda t: t.get("amenity") == "fuel")
    build.extract_sights(work)
    stats["sights"] = build.build_sights(work, os.path.join(out, "sights.json"))
    build.extract_pois(work, None if info.get("limits") else build.POI_FILTERS_FOREIGN)
    rows = build.poi_rows(work, out)
    with gzip.open(os.path.join(out, "pois.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
    stats["pois"] = len(rows)
    runs = moto_tiles.read_curves(work)
    with gzip.open(os.path.join(out, "curves.json.gz"), "wt") as f:
        json.dump([[level, [[round(x, 5), round(y, 5)] for x, y in coords]] for level, coords in runs], f, separators=(",", ":"))
    stats["curvesKm"] = round(sum((len(c) - 1) * moto_tiles.STEP for _, c in runs) / 1000)
    return stats


def sane(stats, previous):
    """List of problems: counts that dropped a lot against the previous accepted build."""
    problems = []
    for key in CHECKED:
        old, new = (previous or {}).get(key), stats.get(key)
        if isinstance(old, (int, float)) and old >= 100 and (new or 0) < old * DROP:
            problems.append(f"{key}: {new} (minule {old})")
    return problems


def main(cc, work, out, previous_dir=None):
    previous = None
    if previous_dir and os.path.exists(os.path.join(previous_dir, "stats.json")):
        with open(os.path.join(previous_dir, "stats.json"), encoding="utf-8") as f:
            previous = json.load(f)
    try:
        stats = run(cc, work, out)
        problems = sane(stats, previous)
    except Exception as error:  # noqa: BLE001 - a broken country must not stop the others
        stats, problems = {"country": cc}, [f"chyba: {error}"]
    if problems and previous is not None:
        print(f"::warning::{cc}: data vypadají špatně ({'; '.join(problems)}) – zůstává minulá verze.")
        shutil.rmtree(out, ignore_errors=True)
        shutil.copytree(previous_dir, out)
        with open(os.path.join(out, "stats.json"), encoding="utf-8") as f:
            kept = json.load(f)
        kept["kept"] = True
        kept["problems"] = problems
        with open(os.path.join(out, "stats.json"), "w", encoding="utf-8") as f:
            json.dump(kept, f, ensure_ascii=False)
        if os.path.exists(os.path.join(out, "ACCEPTED")):
            os.remove(os.path.join(out, "ACCEPTED"))
        return
    if problems:
        print(f"::warning::{cc}: {'; '.join(problems)} (bez minulé verze k porovnání)")
        if any(p.startswith("chyba") for p in problems):
            sys.exit(f"{cc}: sestavení selhalo")
    with open(os.path.join(out, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False)
    with open(os.path.join(out, "ACCEPTED"), "w") as f:
        f.write("ok")
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:5])
