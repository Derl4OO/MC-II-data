"""MotoCesta map style (day and night) for MapLibre, our own design: nothing taken from Mapbox styles.

Data: OpenMapTiles schema vector tiles. For now from OpenFreeMap (free, no key, no limits, © OpenMapTiles,
© OpenStreetMap contributors); later from our own tiles on Cloudflare (only TILES and GLYPHS change).
Fonts: Noto Sans (SIL Open Font License). No 3D buildings, no terrain, no satellite.

Design (approved 3. 11. 2026): stronger roads, place names ~50 % larger, motorways toned down,
only rider places (fuel, cafés), own colours; night = the same style, dark.
Warmer day colours, fields, industry, main roads slightly yellow and peaks (Julien: "studenější a chudější než Mapbox").
Writes v1/style/day.json and v1/style/night.json. Only the standard library is used.
"""
import json
import os
import sys

TILES = "https://tiles.openfreemap.org/planet"
GLYPHS = "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf"
ATTRIBUTION = "© OpenMapTiles © přispěvatelé OpenStreetMap"
REGULAR, BOLD = ["Noto Sans Regular"], ["Noto Sans Bold"]

PALETTES = {
    "day": {
        "background": "#f7f1e3", "wood": "#bfdaa6", "grass": "#d6e8c0", "residential": "#f0e4d2",
        "farmland": "#f2ead0", "industrial": "#ece4e4", "cemetery": "#dbe6d2",
        "water": "#a3cbef", "waterway": "#86b8e6", "building": "#e6dccd",
        "motorway": "#c7c9d2", "motorway_case": "#a9acb8",
        "trunk": "#fbd27a", "secondary": "#fdeeb8", "major": "#ffffff", "major_case": "#b39a78", "minor": "#ffffff", "minor_case": "#cfc5b4",
        "rail": "#b9b4ac", "boundary": "#9b8fb0",
        "label": "#2a241c", "label_soft": "#5a5247", "halo": "#f6f1e7", "water_label": "#3d6f9e", "peak": "#7a5b3a",
        "poi": "#e8590c", "poi_stroke": "#ffffff",
    },
    "night": {
        "background": "#1b1e24", "wood": "#1f2a22", "grass": "#212a22", "residential": "#22262d",
        "farmland": "#1e2126", "industrial": "#25252b", "cemetery": "#1f2822",
        "water": "#1d2d40", "waterway": "#26405c", "building": "#2a2e36",
        "motorway": "#5c616d", "motorway_case": "#454955",
        "trunk": "#d9b768", "secondary": "#c9bc94", "major": "#c9ccd4", "major_case": "#1b1e24", "minor": "#7d828e", "minor_case": "#1b1e24",
        "rail": "#4a4e57", "boundary": "#7a6f92",
        "label": "#f1f2f4", "label_soft": "#b9bcc4", "halo": "#1b1e24", "water_label": "#7fa6cf", "peak": "#c9a27a",
        "poi": "#f06a1f", "poi_stroke": "#1b1e24",
    },
}

MAJOR = ["trunk", "primary", "secondary", "tertiary"]
MINOR = ["minor", "service"]


def width(stops):
    """Road width that grows with zoom (exponential, like a map should)."""
    expr = ["interpolate", ["exponential", 1.5], ["zoom"]]
    for z, w in stops:
        expr += [z, w]
    return expr


def road(layer_id, classes, color, line_width, minzoom=0, dash=None):
    paint = {"line-color": color, "line-width": line_width}
    if dash:
        paint["line-dasharray"] = dash
    return {"id": layer_id, "type": "line", "source": "omt", "source-layer": "transportation", "minzoom": minzoom,
            "filter": ["all", ["in", ["get", "class"], ["literal", classes]], ["!=", ["get", "brunnel"], "tunnel"]],
            "layout": {"line-cap": "round", "line-join": "round"}, "paint": paint}


def build(name, palette=None, scale=1.0):
    """palette/scale: other looks for the preview page (variants to choose from)."""
    p = dict(PALETTES[name], **(palette or {}))
    global width
    plain = width
    width = lambda stops: plain([(z, w * scale) for z, w in stops])  # noqa: E731 - road widths of the variant
    try:
        return _build(name, p)
    finally:
        width = plain


def _build(name, p):
    major_w = width([(6, 0.8), (10, 2.4), (13, 5), (16, 14), (18, 30)])
    major_case = width([(6, 1.4), (10, 3.6), (13, 7), (16, 17), (18, 34)])
    minor_w = width([(11, 0.6), (13, 1.8), (16, 7), (18, 16)])
    minor_case = width([(11, 1.2), (13, 2.8), (16, 9), (18, 19)])
    motorway_w = width([(5, 0.8), (10, 2.2), (13, 4), (16, 10), (18, 22)])
    motorway_case = width([(5, 1.2), (10, 3), (13, 5.2), (16, 12), (18, 25)])
    layers = [
        {"id": "background", "type": "background", "paint": {"background-color": p["background"]}},
        {"id": "residential", "type": "fill", "source": "omt", "source-layer": "landuse", "maxzoom": 16,
         "filter": ["in", ["get", "class"], ["literal", ["residential", "suburb", "neighbourhood"]]],
         "paint": {"fill-color": p["residential"]}},
        {"id": "farmland", "type": "fill", "source": "omt", "source-layer": "landcover",
         "filter": ["in", ["get", "class"], ["literal", ["farmland", "grass"]]], "paint": {"fill-color": p["farmland"]}},
        {"id": "industrial", "type": "fill", "source": "omt", "source-layer": "landuse", "minzoom": 11,
         "filter": ["in", ["get", "class"], ["literal", ["industrial", "commercial", "retail"]]], "paint": {"fill-color": p["industrial"]}},
        {"id": "cemetery", "type": "fill", "source": "omt", "source-layer": "landuse", "minzoom": 12,
         "filter": ["==", ["get", "class"], "cemetery"], "paint": {"fill-color": p["cemetery"]}},
        {"id": "wood", "type": "fill", "source": "omt", "source-layer": "landcover",
         "filter": ["==", ["get", "class"], "wood"], "paint": {"fill-color": p["wood"]}},
        {"id": "grass", "type": "fill", "source": "omt", "source-layer": "park",
         "paint": {"fill-color": p["grass"], "fill-opacity": 0.7}},
        {"id": "water", "type": "fill", "source": "omt", "source-layer": "water",
         "filter": ["!=", ["get", "brunnel"], "tunnel"], "paint": {"fill-color": p["water"]}},
        {"id": "waterway", "type": "line", "source": "omt", "source-layer": "waterway", "minzoom": 9,
         "filter": ["in", ["get", "class"], ["literal", ["river", "canal", "stream"]]],
         "paint": {"line-color": p["waterway"], "line-width": width([(9, 0.6), (14, 2), (18, 6)])}},
        {"id": "building", "type": "fill", "source": "omt", "source-layer": "building", "minzoom": 15,
         "paint": {"fill-color": p["building"], "fill-opacity": 0.8}},
        {"id": "boundary-country", "type": "line", "source": "omt", "source-layer": "boundary",
         "filter": ["all", ["==", ["get", "admin_level"], 2], ["!=", ["get", "maritime"], 1]],
         "paint": {"line-color": p["boundary"], "line-width": width([(3, 0.8), (10, 2), (14, 3)]), "line-dasharray": [3, 2]}},
        {"id": "rail", "type": "line", "source": "omt", "source-layer": "transportation", "minzoom": 11,
         "filter": ["==", ["get", "class"], "rail"],
         "paint": {"line-color": p["rail"], "line-width": width([(11, 0.6), (16, 2)])}},
        # Unpaved tracks are not for us (routes avoid them): only faint at close zoom, dashed.
        road("track", ["track"], p["minor_case"], width([(14, 0.6), (18, 2)]), minzoom=14, dash=[2, 2]),
        road("minor-case", MINOR, p["minor_case"], minor_case, minzoom=11),
        road("minor", MINOR, p["minor"], minor_w, minzoom=11),
        road("motorway-case", ["motorway"], p["motorway_case"], motorway_case),
        road("motorway", ["motorway"], p["motorway"], motorway_w),
        road("major-case", MAJOR, p["major_case"], major_case, minzoom=6),
        road("major", ["tertiary"], p["major"], major_w, minzoom=6),
        road("secondary", ["secondary"], p["secondary"], major_w, minzoom=6),
        # Main roads (trunk, primary) slightly warm, so the network reads at a glance (not a cold grey map).
        road("trunk", ["trunk", "primary"], p["trunk"], major_w, minzoom=6),
        {"id": "road-name", "type": "symbol", "source": "omt", "source-layer": "transportation_name", "minzoom": 13,
         "filter": ["in", ["get", "class"], ["literal", MAJOR + MINOR]],
         "layout": {"symbol-placement": "line", "text-field": ["coalesce", ["get", "name:cs"], ["get", "name"]],
                    "text-font": REGULAR, "text-size": width([(13, 11), (17, 15)]), "text-max-angle": 30},
         "paint": {"text-color": p["label_soft"], "text-halo-color": p["halo"], "text-halo-width": 1.5}},
        {"id": "road-ref", "type": "symbol", "source": "omt", "source-layer": "transportation_name", "minzoom": 9,
         "filter": ["all", ["has", "ref"], ["in", ["get", "class"], ["literal", ["motorway", "trunk", "primary", "secondary"]]]],
         "layout": {"symbol-placement": "line", "symbol-spacing": 400, "text-field": ["get", "ref"], "text-font": BOLD,
                    "text-size": 12, "text-rotation-alignment": "viewport"},
         "paint": {"text-color": p["label_soft"], "text-halo-color": p["halo"], "text-halo-width": 2}},
        {"id": "water-name", "type": "symbol", "source": "omt", "source-layer": "water_name", "minzoom": 11,
         "layout": {"text-field": ["coalesce", ["get", "name:cs"], ["get", "name"]], "text-font": ["Noto Sans Italic"], "text-size": 13},
         "paint": {"text-color": p["water_label"], "text-halo-color": p["halo"], "text-halo-width": 1.5}},
        # Rider places only: fuel and cafés (orange dots); the apps add their own icons for their own data.
        {"id": "poi-rider", "type": "circle", "source": "omt", "source-layer": "poi", "minzoom": 13,
         "filter": ["in", ["get", "class"], ["literal", ["fuel", "cafe"]]],
         "paint": {"circle-color": p["poi"], "circle-radius": width([(13, 4), (17, 8)]),
                   "circle-stroke-color": p["poi_stroke"], "circle-stroke-width": 2}},
        {"id": "poi-rider-name", "type": "symbol", "source": "omt", "source-layer": "poi", "minzoom": 15,
         "filter": ["in", ["get", "class"], ["literal", ["fuel", "cafe"]]],
         "layout": {"text-field": ["coalesce", ["get", "name:cs"], ["get", "name"]], "text-font": REGULAR, "text-size": 13,
                    "text-offset": [0, 1.2], "text-anchor": "top"},
         "paint": {"text-color": p["label_soft"], "text-halo-color": p["halo"], "text-halo-width": 1.5}},
        # Peaks with height (riders navigate by hills and passes).
        {"id": "peak", "type": "symbol", "source": "omt", "source-layer": "mountain_peak", "minzoom": 11,
         "filter": ["all", ["has", "name"], ["has", "ele"]],
         "layout": {"text-field": ["concat", ["coalesce", ["get", "name:cs"], ["get", "name"]], "\n", ["to-string", ["get", "ele"]], " m"],
                    "text-font": REGULAR, "text-size": 12, "text-max-width": 8},
         "paint": {"text-color": p["peak"], "text-halo-color": p["halo"], "text-halo-width": 1.5}},
        # Place names about 50 % larger than a usual map, bold, readable from the handlebars.
        {"id": "place-village", "type": "symbol", "source": "omt", "source-layer": "place", "minzoom": 10,
         "filter": ["in", ["get", "class"], ["literal", ["village", "hamlet", "suburb"]]],
         "layout": {"text-field": ["coalesce", ["get", "name:cs"], ["get", "name"]], "text-font": BOLD,
                    "text-size": width([(10, 13), (14, 20), (17, 24)]), "text-max-width": 8},
         "paint": {"text-color": p["label"], "text-halo-color": p["halo"], "text-halo-width": 2}},
        {"id": "place-town", "type": "symbol", "source": "omt", "source-layer": "place", "minzoom": 7,
         "filter": ["==", ["get", "class"], "town"],
         "layout": {"text-field": ["coalesce", ["get", "name:cs"], ["get", "name"]], "text-font": BOLD,
                    "text-size": width([(7, 13), (11, 20), (15, 26)]), "text-max-width": 8},
         "paint": {"text-color": p["label"], "text-halo-color": p["halo"], "text-halo-width": 2}},
        {"id": "place-city", "type": "symbol", "source": "omt", "source-layer": "place", "minzoom": 4,
         "filter": ["==", ["get", "class"], "city"],
         "layout": {"text-field": ["coalesce", ["get", "name:cs"], ["get", "name"]], "text-font": BOLD,
                    "text-size": width([(4, 13), (8, 20), (12, 28)]), "text-max-width": 8},
         "paint": {"text-color": p["label"], "text-halo-color": p["halo"], "text-halo-width": 2.5}},
    ]
    return {"version": 8, "name": f"MotoCesta {name}", "glyphs": GLYPHS,
            "sources": {"omt": {"type": "vector", "url": TILES, "attribution": ATTRIBUTION}},
            "layers": layers}


def main(out):
    folder = os.path.join(out, "style")
    os.makedirs(folder, exist_ok=True)
    for name in PALETTES:
        with open(os.path.join(folder, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(build(name), f, ensure_ascii=False, separators=(",", ":"))
    return list(PALETTES)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "v1")
