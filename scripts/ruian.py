"""Address catalogue for the Czech Republic from RÚIAN (ČÚZK open data, licence CC BY 4.0).

The app searches addresses here first: it may store them as favourites (unlike Mapbox search results,
which the Mapbox terms forbid storing), it works without signal once a file is downloaded, and it costs nothing.

Output: v1/addr/<3 letters>.bin (raw DEFLATE JSON, same as the other catalogues). One row per street
(or per part of a village without streets):
    [street, town, part, postcode, [[number, lat, lon], ...]]
A street is listed under the first three letters of each of its words (at most four words).
Only the standard library is used.
"""
import csv
import datetime
import io
import math
import os
import re
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict

# --- S-JTSK (EPSG:5514, Křovák) -> WGS 84 -------------------------------------------------------------
_A = 6377397.155                      # Bessel 1841
_E2 = 0.006674372230614
_E = math.sqrt(_E2)
_PHI_C = math.radians(49.5)
_LAM_0 = math.radians(24 + 50 / 60)   # Greenwich
_ALPHA_C = math.radians(30 + 17 / 60 + 17.30311 / 3600)
_PHI_P = math.radians(78.5)
_K_P = 0.9999
_AA = _A * math.sqrt(1 - _E2) / (1 - _E2 * math.sin(_PHI_C) ** 2)
_B = math.sqrt(1 + _E2 * math.cos(_PHI_C) ** 4 / (1 - _E2))
_GAMMA_0 = math.asin(math.sin(_PHI_C) / _B)
_T_0 = (math.tan(math.pi / 4 + _GAMMA_0 / 2)
        * ((1 + _E * math.sin(_PHI_C)) / (1 - _E * math.sin(_PHI_C))) ** (_E * _B / 2)
        / math.tan(math.pi / 4 + _PHI_C / 2) ** _B)
_N = math.sin(_PHI_P)
_R_0 = _K_P * _AA / math.tan(_PHI_P)
# Bessel -> WGS 84, position vector (the usual parameters of EPSG:5514 in PROJ: towgs84=570.8,85.7,462.8,4.998,1.587,5.261,3.56)
_TX, _TY, _TZ = 570.8, 85.7, 462.8
_RX, _RY, _RZ = (math.radians(v / 3600) for v in (4.998, 1.587, 5.261))
_S = 3.56e-6
_WGS_A = 6378137.0
_WGS_E2 = 0.00669437999014


def krovak_forward(lat, lon):
    """Bessel latitude/longitude in degrees -> (southing X, westing Y) in metres. Used only for the self-test."""
    phi, lam = math.radians(lat), math.radians(lon)
    u = 2 * (math.atan(_T_0 * math.tan(phi / 2 + math.pi / 4) ** _B
                       / ((1 + _E * math.sin(phi)) / (1 - _E * math.sin(phi))) ** (_E * _B / 2)) - math.pi / 4)
    v = _B * (_LAM_0 - lam)
    t = math.asin(math.cos(_ALPHA_C) * math.sin(u) + math.sin(_ALPHA_C) * math.cos(u) * math.cos(v))
    d = math.asin(math.cos(u) * math.sin(v) / math.cos(t))
    theta = _N * d
    r = _R_0 * math.tan(math.pi / 4 + _PHI_P / 2) ** _N / math.tan(t / 2 + math.pi / 4) ** _N
    return r * math.cos(theta), r * math.sin(theta)


def krovak_inverse(x, y):
    """(southing X, westing Y) in metres (positive, as in RÚIAN) -> Bessel latitude/longitude in degrees."""
    r = math.hypot(x, y)
    theta = math.atan2(y, x)
    d = theta / math.sin(_PHI_P)
    t = 2 * (math.atan((_R_0 / r) ** (1 / _N) * math.tan(math.pi / 4 + _PHI_P / 2)) - math.pi / 4)
    u = math.asin(math.cos(_ALPHA_C) * math.sin(t) - math.sin(_ALPHA_C) * math.cos(t) * math.cos(d))
    v = math.asin(math.cos(t) * math.sin(d) / math.cos(u))
    lam = _LAM_0 - v / _B
    phi = u
    for _ in range(8):
        phi = 2 * (math.atan(_T_0 ** (-1 / _B) * math.tan(u / 2 + math.pi / 4) ** (1 / _B)
                             * ((1 + _E * math.sin(phi)) / (1 - _E * math.sin(phi))) ** (_E / 2)) - math.pi / 4)
    return math.degrees(phi), math.degrees(lam)


def _to_ecef(lat, lon, a, e2):
    phi, lam = math.radians(lat), math.radians(lon)
    n = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    return n * math.cos(phi) * math.cos(lam), n * math.cos(phi) * math.sin(lam), n * (1 - e2) * math.sin(phi)


def _from_ecef(x, y, z, a, e2):
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    phi = math.atan2(z, p * (1 - e2))
    for _ in range(6):
        n = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
        phi = math.atan2(z + e2 * n * math.sin(phi), p)
    return math.degrees(phi), math.degrees(lon)


def sjtsk_to_wgs84(x, y):
    """RÚIAN 'Souřadnice X' (southing) and 'Souřadnice Y' (westing) -> WGS 84 (lat, lon), about 1 m accurate."""
    lat_b, lon_b = krovak_inverse(abs(x), abs(y))
    bx, by, bz = _to_ecef(lat_b, lon_b, _A, _E2)
    k = 1 + _S
    wx = _TX + k * (bx - _RZ * by + _RY * bz)
    wy = _TY + k * (_RZ * bx + by - _RX * bz)
    wz = _TZ + k * (-_RY * bx + _RX * by + bz)
    return _from_ecef(wx, wy, wz, _WGS_A, _WGS_E2)


# --- Download ------------------------------------------------------------------------------------------
def _candidate_urls(today=None):
    """The file of the last day of the previous month (published on the 1st), then the month before."""
    today = today or datetime.date.today()
    first = today.replace(day=1)
    urls = []
    for _ in range(2):
        last = first - datetime.timedelta(days=1)
        urls.append(f"https://vdp.cuzk.cz/vymenny_format/csv/{last:%Y%m%d}_OB_ADR_csv.zip")
        first = last.replace(day=1)
    return urls


def _from_atom():
    """Fallback: the ZIP link from the official ATOM feed."""
    with urllib.request.urlopen("https://atom.cuzk.gov.cz/RUIAN-CSV-ADR-ST/RUIAN-CSV-ADR-ST.xml", timeout=60) as response:
        feed = response.read().decode("utf-8", "replace")
    links = re.findall(r'href="([^"]+\.zip)"', feed)
    return links[:1]


def download(path):
    errors = []
    urls = _candidate_urls()
    try:
        urls += _from_atom()
    except Exception as error:  # noqa: BLE001 - only a fallback
        errors.append(f"atom: {error}")
    for url in urls:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "MotoCesta-data (github.com/Derl4OO/MC-II-data)"})
            with urllib.request.urlopen(request, timeout=300) as response, open(path, "wb") as f:
                while chunk := response.read(1 << 20):
                    f.write(chunk)
            if zipfile.is_zipfile(path):
                return url
            errors.append(f"{url}: není ZIP")
        except Exception as error:  # noqa: BLE001
            errors.append(f"{url}: {error}")
    raise RuntimeError("RÚIAN se nepodařilo stáhnout: " + "; ".join(errors))


# --- Catalogue -----------------------------------------------------------------------------------------
def normalize(text):
    plain = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def _column(header, *names):
    wanted = [normalize(n) for n in names]
    for i, h in enumerate(header):
        if normalize(h) in wanted:
            return i
    raise KeyError(names[0])


def read_rows(zip_path):
    """Yield (street, town, part, postcode, number, lat, lon) for every address point."""
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if not info.filename.lower().endswith(".csv"):
                continue
            raw = archive.read(info)
            try:
                text = raw.decode("cp1250")
            except UnicodeDecodeError:
                text = raw.decode("utf-8", "replace")
            reader = csv.reader(io.StringIO(text), delimiter=";")
            header = next(reader, None)
            if not header:
                continue
            c_town = _column(header, "Název obce")
            c_momc = _column(header, "Název MOMC")
            c_part = _column(header, "Název části obce")
            c_street = _column(header, "Název ulice")
            c_type = _column(header, "Typ SO")
            c_house = _column(header, "Číslo domovní")
            c_orient = _column(header, "Číslo orientační")
            c_sign = _column(header, "Znak čísla orientačního")
            c_psc = _column(header, "PSČ")
            c_y = _column(header, "Souřadnice Y")
            c_x = _column(header, "Souřadnice X")
            for row in reader:
                try:
                    x, y = float(row[c_x].replace(",", ".")), float(row[c_y].replace(",", "."))
                except (ValueError, IndexError):
                    continue
                if x == 0 or y == 0:
                    continue
                lat, lon = sjtsk_to_wgs84(x, y)
                house = row[c_house].strip()
                if "ev" in row[c_type].lower():
                    house = "ev. " + house
                orient = row[c_orient].strip() + row[c_sign].strip()
                street = row[c_street].strip()
                part = row[c_part].strip()
                town = row[c_town].strip()
                momc = row[c_momc].strip()
                if momc and momc != town:
                    town = f"{town} – {momc}" if not momc.startswith(town) else momc
                number = f"{house}/{orient}" if street and orient else house
                yield street, town, part, row[c_psc].strip(), number, lat, lon


def build(zip_path, out_dir):
    groups = defaultdict(list)
    for street, town, part, psc, number, lat, lon in read_rows(zip_path):
        name = street or part
        groups[(name, town, part if street else "", psc)].append([number, round(lat, 5), round(lon, 5)])
    by_key = defaultdict(list)
    for (name, town, part, psc), points in groups.items():
        row = [name, town, part, psc, points]
        for key in {w[:3] for w in normalize(name).split()[:4] if len(w) >= 3}:
            by_key[key].append(row)
    os.makedirs(os.path.join(out_dir, "addr"), exist_ok=True)
    import json
    import zlib
    for key, rows in by_key.items():
        payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
        with open(os.path.join(out_dir, "addr", f"{key}.bin"), "wb") as f:
            f.write(compressor.compress(payload) + compressor.flush())
    return sum(len(p) for p in groups.values()), len(by_key)


def build_addresses(work, out_dir):
    """Download RÚIAN and write v1/addr. Returns (address points, files, source URL)."""
    path = os.path.join(work, "ruian-adr.zip")
    url = download(path)
    points, files = build(path, out_dir)
    os.remove(path)
    return points, files, url


if __name__ == "__main__":
    # Self-test of the conversion: EPSG Guidance Note 7-2 example (Bessel 50°12'32.442" N, 16°50'59.179" E).
    sx, wy = krovak_forward(50 + 12 / 60 + 32.442 / 3600, 16 + 50 / 60 + 59.179 / 3600)
    print("forward", round(sx, 2), round(wy, 2), "expected 1050538.63 568991.00")
    print("inverse", krovak_inverse(sx, wy))
