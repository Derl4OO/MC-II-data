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
import shutil
import sys

TILES = "https://tiles.openfreemap.org/planet"
GLYPHS = "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf"
# Our own icons (road number shields, fuel, café), drawn by Claude: style-assets/sprite*.png/json.
SPRITE = "https://derl4oo.github.io/MC-II-data/v1/style/sprite"
# Our layer (moto_tiles.py): curvy roads in two levels and our places (castles, viewpoints, motorests…).
MOTO_TILES = "https://derl4oo.github.io/MC-II-data/v1/moto/{z}/{x}/{y}.pbf"
# Flat hill shading (not 3D): open elevation tiles on AWS Open Data (Terrain Tiles, Mapzen), no key.
DEM_TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
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
        "protected": "#6f9a5a", "tunnel": "#d9d2c6", "outline": "#d3c8b6", "wetland": "#dbe8d8",
        "curve1": "#f6a04d", "curve2": "#e03131", "shadow": "#6b5a45", "highlight": "#fffaf0",
    },
    # Night: the same style, warm and dimmed (no cold blue-grey glare in the dark).
    "night": {
        "background": "#1f1c19", "wood": "#232a1f", "grass": "#242a20", "residential": "#26221e",
        "farmland": "#211e1a", "industrial": "#28241f", "cemetery": "#232920",
        "water": "#1a2833", "waterway": "#223a4c", "building": "#2c2823",
        "motorway": "#6b5c48", "motorway_case": "#4a4034",
        "trunk": "#c9a35a", "secondary": "#b8a682", "major": "#bdb3a4", "major_case": "#1f1c19", "minor": "#7f776b", "minor_case": "#1f1c19",
        "rail": "#4d4740", "boundary": "#7d6e8c",
        "label": "#efe8dc", "label_soft": "#b8ad9c", "halo": "#1f1c19", "water_label": "#7f9fba", "peak": "#c9a27a",
        "poi": "#e8620f", "poi_stroke": "#1f1c19",
        "protected": "#5f8a52", "tunnel": "#3b3630", "outline": "#35302a", "wetland": "#202722",
        "curve1": "#d9873a", "curve2": "#c9302c", "shadow": "#000000", "highlight": "#3a342c",
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


# Looks approved for the preview 3. 11. 2026 (Julien + Codex + Claude): Moto Light for planning, Topo Touring
# for browsing a trip (stronger hills and curves), Rider Focus for riding (calm, big, few labels). Day light, night dark.
_LIGHT_COOL = {"background": "#f4f2ec", "wood": "#dbe6d1", "grass": "#e4ecd9", "residential": "#eeeae2", "farmland": "#f4f2ec",
          "industrial": "#ebe8e2", "cemetery": "#dfe8d6", "wetland": "#dfe9e0", "water": "#d3e5ea", "waterway": "#b3d3de",
          "building": "#e6e1d8", "outline": "#d8d1c4", "motorway": "#ead9c0", "motorway_case": "#cdb795",
          "trunk": "#ffffff", "secondary": "#ffffff", "major": "#ffffff", "major_case": "#c9c3b8", "minor": "#ffffff",
          "minor_case": "#dbd5ca", "tunnel": "#e4dfd6", "rail": "#c9c4bb", "boundary": "#a79cb6",
          "label": "#2a2722", "label_soft": "#6b665c", "halo": "#f4f2ec", "water_label": "#3f6f86", "peak": "#7a6a55",
          "poi": "#d9733a", "poi_stroke": "#ffffff", "protected": "#7c9a6a",
          "curve1": "#c7704f", "curve2": "#b0402e", "curve_opacity": 0.3, "shadow": "#8a7a65", "highlight": "#fffaf0", "hillshade": 0.22}
# Warmer and livelier than the first version (Julien 3. 11.: "moc studená / šedá").
_LIGHT = {"background": "#f6f1e6", "wood": "#cde1ba", "grass": "#dbeac7", "residential": "#efe6d7", "farmland": "#f4eede",
          "industrial": "#ece5dc", "cemetery": "#d9e6cc", "wetland": "#d9e8d6", "water": "#b6daeb", "waterway": "#96c7e2",
          "building": "#e8dccb", "outline": "#d9cbb5", "motorway": "#f2cf9f", "motorway_case": "#d6a466",
          "trunk": "#fff3d6", "secondary": "#ffffff", "major": "#ffffff", "major_case": "#c2b197", "minor": "#ffffff",
          "minor_case": "#d9ccb8", "tunnel": "#e6dccd", "rail": "#c7bdb0", "boundary": "#a593b3",
          "label": "#2b261f", "label_soft": "#6a5f50", "halo": "#f6f1e6", "water_label": "#2f6d93", "peak": "#7a5b3a",
          "poi": "#d9733a", "poi_stroke": "#ffffff", "protected": "#6f9a5a",
          "curve1": "#d0703f", "curve2": "#b8402e", "curve_opacity": 0.32, "shadow": "#8a6f52", "highlight": "#fffaf0", "hillshade": 0.26}
_DARK = {"background": "#211f1b", "wood": "#262c21", "grass": "#262b20", "residential": "#2a2721", "farmland": "#22201c",
         "industrial": "#2b2823", "cemetery": "#252a20", "wetland": "#222823", "water": "#1b2b35", "waterway": "#25445a",
         "building": "#322e27", "outline": "#3c372f", "motorway": "#73603f", "motorway_case": "#15130f",
         "trunk": "#c9b98f", "secondary": "#a9a393", "major": "#9c9686", "major_case": "#15130f", "minor": "#746e62",
         "minor_case": "#15130f", "tunnel": "#3c3830", "rail": "#4f4a41", "boundary": "#7d6e8c",
         "label": "#efe8db", "label_soft": "#b9ad99", "halo": "#211f1b", "water_label": "#86a8bd", "peak": "#c9a27a",
         "poi": "#e8843f", "poi_stroke": "#211f1b", "protected": "#5f8a52",
         "curve1": "#d9873a", "curve2": "#c9302c", "curve_opacity": 0.35, "shadow": "#000000", "highlight": "#3a342c", "hillshade": 0.2}
_FOCUS_HIDE = ["poi-rider-name", "places", "protected-line", "protected-name", "peak", "pass", "building", "wetland",
               "cemetery", "industrial", "curves-1", "curves-2", "oneway", "water-name"]
LOOKS = {
    "moto-light": ("Moto Light – plánování", {"day": _LIGHT, "night": _DARK}, 1.0),
    "topo-touring": ("Topo Touring – prohlížení výletu (kopce a zatáčky výrazněji)",
                     {"day": dict(_LIGHT, hillshade=0.45, curve_opacity=0.5), "night": dict(_DARK, hillshade=0.35, curve_opacity=0.5)}, 1.0),
    "rider-focus": ("Rider Focus – navigace (klidná, velká, málo popisků)",
                    {"day": dict(_LIGHT, major_case="#a8977e", minor_case="#c9bba6", hillshade=0.14, hide=_FOCUS_HIDE),
                     "night": dict(_DARK, trunk="#d6c79c", secondary="#bdb5a2", major="#aea796", hillshade=0.12, hide=_FOCUS_HIDE)}, 1.25),
}


def build_look(look, name):
    _, palettes, scale = LOOKS[look]
    return build(name, palettes[name], scale)


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
    if p.get("extras", True):
        tune(layers, p, major_w, minor_w, name)
    hidden = set(p.get("hide", []))
    layers[:] = [layer for layer in layers if layer["id"] not in hidden]
    style = {"version": 8, "name": f"MotoCesta {name}", "glyphs": GLYPHS,
             "sources": {"omt": {"type": "vector", "url": TILES, "attribution": ATTRIBUTION}},
             "layers": layers}
    if p.get("extras", True):
        style["sprite"] = SPRITE
        style["sources"]["moto"] = {"type": "vector", "tiles": [MOTO_TILES], "minzoom": 8, "maxzoom": 12,
                                    "attribution": "© přispěvatelé OpenStreetMap, MotoCesta"}
        style["sources"]["dem"] = {"type": "raster-dem", "tiles": [DEM_TILES], "encoding": "terrarium", "tileSize": 256,
                                   "maxzoom": 12, "attribution": "Terrain Tiles (Mapzen, AWS Open Data)"}
    return style


def tune(layers, p, major_w, minor_w, name):
    """Finer details (Julien, 3. 11.: "lze vzhled ještě vytunit?"): tunnels, wetlands, building outlines,
    protected areas (CHKO, national parks) with names, mountain passes, bigger towns win label space."""
    def after(layer_id, *new):
        index = next(i for i, layer in enumerate(layers) if layer["id"] == layer_id) + 1
        layers[index:index] = list(new)

    after("farmland",
          {"id": "wetland", "type": "fill", "source": "omt", "source-layer": "landcover", "minzoom": 10,
           "filter": ["==", ["get", "class"], "wetland"], "paint": {"fill-color": p["wetland"]}})
    after("grass",
          {"id": "protected-line", "type": "line", "source": "omt", "source-layer": "park", "minzoom": 8,
           "filter": ["in", ["get", "class"], ["literal", ["national_park", "protected_area", "nature_reserve"]]],
           "paint": {"line-color": p["protected"], "line-opacity": 0.55, "line-width": width([(8, 1), (13, 2.5)]),
                     "line-dasharray": [4, 2]}})
    for layer in layers:
        if layer["id"] == "building":
            layer["paint"]["fill-outline-color"] = p["outline"]
    # Tunnels: the same roads, faded and dashed, under everything else.
    after("rail",
          {"id": "tunnel", "type": "line", "source": "omt", "source-layer": "transportation", "minzoom": 11,
           "filter": ["all", ["==", ["get", "brunnel"], "tunnel"],
                      ["in", ["get", "class"], ["literal", ["motorway", "trunk", "primary", "secondary", "tertiary", "minor"]]]],
           "layout": {"line-join": "round"},
           "paint": {"line-color": p["tunnel"], "line-width": major_w, "line-dasharray": [1, 0.6]}})
    after("peak",
          {"id": "pass", "type": "symbol", "source": "omt", "source-layer": "mountain_peak", "minzoom": 10,
           "filter": ["all", ["==", ["get", "class"], "saddle"], ["has", "name"]],
           "layout": {"text-field": ["concat", ["coalesce", ["get", "name:cs"], ["get", "name"]],
                                     ["case", ["has", "ele"], ["concat", "\n", ["to-string", ["get", "ele"]], " m"], ""]],
                      "text-font": BOLD, "text-size": 13, "text-max-width": 8},
           "paint": {"text-color": p["peak"], "text-halo-color": p["halo"], "text-halo-width": 2}},
          {"id": "protected-name", "type": "symbol", "source": "omt", "source-layer": "park", "minzoom": 9, "maxzoom": 13,
           "filter": ["all", ["has", "name"], ["in", ["get", "class"], ["literal", ["national_park", "protected_area"]]]],
           "layout": {"text-field": ["coalesce", ["get", "name:cs"], ["get", "name"]], "text-font": ["Noto Sans Italic"],
                      "text-size": 13, "text-max-width": 9},
           "paint": {"text-color": p["protected"], "text-halo-color": p["halo"], "text-halo-width": 1.5}})
    # Flat hill shading (Julien 3. 11.: ok if not 3D terrain), soft and warm.
    after("protected-line",
          {"id": "hillshade", "type": "hillshade", "source": "dem", "maxzoom": 16,
           "paint": {"hillshade-exaggeration": p.get("hillshade", 0.3 if name == "day" else 0.22), "hillshade-shadow-color": p["shadow"],
                     "hillshade-highlight-color": p["highlight"], "hillshade-accent-color": p["shadow"],
                     "hillshade-illumination-anchor": "map"}})
    # Curvy roads: a glow under the road, light orange (l=1) and sharper red (l=2), as approved 3. 11.
    glow = width([(8, 3), (10, 5), (13, 11), (16, 24), (18, 44)])
    after("tunnel",
          {"id": "curves-1", "type": "line", "source": "moto", "source-layer": "curves", "filter": ["==", ["get", "l"], 1],
           "layout": {"line-cap": "round", "line-join": "round"},
           "paint": {"line-color": p["curve1"], "line-width": glow, "line-opacity": p.get("curve_opacity", 0.55), "line-blur": 1.5}},
          {"id": "curves-2", "type": "line", "source": "moto", "source-layer": "curves", "filter": ["==", ["get", "l"], 2],
           "layout": {"line-cap": "round", "line-join": "round"},
           "paint": {"line-color": p["curve2"], "line-width": glow, "line-opacity": p.get("curve_opacity", 0.6), "line-blur": 1.5}})
    # Bridges: a darker edge, so they read as bridges when close.
    road_colors = ["match", ["get", "class"], ["trunk", "primary"], p["trunk"], "secondary", p["secondary"],
                   "motorway", p["motorway"], ["minor", "service"], p["minor"], p["major"]]
    after("trunk",
          {"id": "bridge-case", "type": "line", "source": "omt", "source-layer": "transportation", "minzoom": 13,
           "filter": ["all", ["==", ["get", "brunnel"], "bridge"], ["in", ["get", "class"], ["literal", MAJOR + MINOR + ["motorway"]]]],
           "layout": {"line-join": "round"}, "paint": {"line-color": p["label_soft"], "line-width": width([(13, 8), (16, 19), (18, 37)])}},
          {"id": "bridge", "type": "line", "source": "omt", "source-layer": "transportation", "minzoom": 13,
           "filter": ["all", ["==", ["get", "brunnel"], "bridge"], ["in", ["get", "class"], ["literal", MAJOR + MINOR + ["motorway"]]]],
           "layout": {"line-join": "round"}, "paint": {"line-color": road_colors, "line-width": major_w}},
          {"id": "oneway", "type": "symbol", "source": "omt", "source-layer": "transportation", "minzoom": 16,
           "filter": ["all", ["in", ["get", "oneway"], ["literal", [1, -1]]], ["in", ["get", "class"], ["literal", MAJOR + MINOR]]],
           "layout": {"symbol-placement": "line", "symbol-spacing": 90, "icon-image": f"oneway-{name}",
                      "icon-rotate": ["case", ["==", ["get", "oneway"], -1], 180, 0], "icon-rotation-alignment": "map",
                      "icon-allow-overlap": True, "icon-size": 0.9}})
    # Our places from MC-II-data (castles, ruins, viewpoints, waterfalls, motorests).
    after("poi-rider-name",
          {"id": "places", "type": "symbol", "source": "moto", "source-layer": "places", "minzoom": 10,
           "layout": {"icon-image": ["concat", ["get", "k"], f"-{name}"], "icon-size": width([(10, 0.7), (16, 1.05)]),
                      "text-field": ["step", ["zoom"], "", 13, ["get", "n"]], "text-font": REGULAR, "text-size": 12,
                      "text-offset": [0, 1.3], "text-anchor": "top", "text-optional": True, "text-max-width": 9},
           "paint": {"text-color": p["label_soft"], "text-halo-color": p["halo"], "text-halo-width": 1.5}})
    # Road numbers in shields (main roads yellow, others white) and icons for fuel and cafés.
    for layer in layers:
        if layer["id"] == "road-ref":
            layer["layout"].update({
                "icon-image": ["case", ["in", ["get", "class"], ["literal", ["motorway", "trunk", "primary"]]],
                               f"shield-main-{name}", f"shield-{name}"],
                "icon-text-fit": "both", "icon-text-fit-padding": [1, 3, 1, 3], "icon-rotation-alignment": "viewport",
                "text-size": 11, "symbol-spacing": 500})
            layer["paint"] = {"text-color": p["label"]}
        if layer["id"] == "poi-rider":
            layer.update({"type": "symbol", "layout": {
                "icon-image": ["concat", ["get", "class"], f"-{name}"], "icon-size": width([(13, 0.75), (17, 1.1)]),
                "icon-allow-overlap": True}, "paint": {}})
    for layer in layers:
        if layer["id"].startswith("place-"):
            layer["layout"]["symbol-sort-key"] = ["coalesce", ["get", "rank"], 99]


def main(out):
    folder = os.path.join(out, "style")
    os.makedirs(folder, exist_ok=True)
    for name in PALETTES:
        with open(os.path.join(folder, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(build(name), f, ensure_ascii=False, separators=(",", ":"))
    # the new looks too (v1/style/<look>-day.json …), the apps switch to them after approval
    for look in LOOKS:
        for name in PALETTES:
            with open(os.path.join(folder, f"{look}-{name}.json"), "w", encoding="utf-8") as f:
                json.dump(build_look(look, name), f, ensure_ascii=False, separators=(",", ":"))
    assets = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "style-assets")
    for file in ("sprite.png", "sprite.json", "sprite@2x.png", "sprite@2x.json"):
        shutil.copy(os.path.join(assets, file), os.path.join(folder, file))
    return list(PALETTES)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "v1")
