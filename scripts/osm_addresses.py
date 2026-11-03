"""Addresses of a country from OpenStreetMap (addr:* tags), in the same format as the Czech RÚIAN catalogue.

Used for every country except CZ (RÚIAN is complete there). Output <out>/addr/<3 letters>.bin, rows
    [street, town, part, postcode, [[number, lat, lon], ...]]
listed under the first three letters of each word of the street (or place) name. merge.py publishes them as
v1/addr/<cc>/… . Data © OpenStreetMap contributors, ODbL. Only the standard library is used.
"""
import json
import os
import zlib
from collections import defaultdict

import build


def build_addresses(opl_path, out_dir):
    groups = defaultdict(list)
    with open(opl_path, encoding="utf-8") as f:
        for line in f:
            if not line or line[0] not in "nw":
                continue
            kind, _, tags, extra = build.parse_line(line)
            number = tags.get("addr:housenumber") or tags.get("addr:conscriptionnumber")
            street = tags.get("addr:street") or tags.get("addr:place")
            if not number or not street:
                continue
            if kind == "n":
                lon, lat = extra
            else:
                pts = [(n[1], n[2]) for n in extra or [] if n[1] is not None]
                if not pts:
                    continue
                lon = sum(p[0] for p in pts) / len(pts)
                lat = sum(p[1] for p in pts) / len(pts)
            if lon is None or lat is None:
                continue
            town = tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village") or ""
            part = tags.get("addr:suburb") or tags.get("addr:hamlet") or ""
            groups[(street, town, part, tags.get("addr:postcode", ""))].append([number, round(lat, 5), round(lon, 5)])
    by_key = defaultdict(list)
    for (street, town, part, postcode), points in groups.items():
        row = [street, town, part, postcode, points]
        for key in {w[:3] for w in build.normalize(street).split()[:4] if len(w) >= 3}:
            by_key[key].append(row)
    folder = os.path.join(out_dir, "addr")
    os.makedirs(folder, exist_ok=True)
    for key, rows in by_key.items():
        payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
        with open(os.path.join(folder, f"{key}.bin"), "wb") as f:
            f.write(compressor.compress(payload) + compressor.flush())
    return sum(len(p) for p in groups.values())
