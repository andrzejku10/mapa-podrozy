"""
Przygotowuje plik data/world.json z granicami państw dla aplikacji.

Źródło: Natural Earth 1:50m Admin 0 – Countries (domena publiczna)
https://www.naturalearthdata.com/

Uruchamiasz to TYLKO jeśli chcesz odświeżyć dane – gotowy world.json
jest już w projekcie. Wymaga: pip install shapely mapbox_earcut numpy

    python tools/prepare_data.py

Co robi skrypt:
  * upraszcza granice (mniejszy plik, szybsze rysowanie na telefonie),
  * przelicza współrzędne na odwzorowanie Millera (ładny kształt mapy),
  * z góry dzieli państwa na trójkąty – dzięki temu aplikacja startuje
    na telefonie w ułamku sekundy zamiast kilku sekund,
  * liczy powierzchnię każdego państwa (do statystyki „% lądów świata”).
"""
import json
import math
import os
import urllib.request

import mapbox_earcut as earcut
import numpy as np
from shapely.geometry import shape
from shapely.ops import transform

URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
       "master/geojson/ne_50m_admin_0_countries.geojson")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "world.json")

KM_PER_DEG = 111.32
TOLERANCE = 0.02  # stopnie – uproszczenie granic

# Krótsze / bardziej potoczne polskie nazwy
NAME_OVERRIDES = {
    "CHN": "Chiny",
    "TWN": "Tajwan",
    "ZAF": "Republika Południowej Afryki",
}


def miller(lon, lat):
    """Odwzorowanie walcowe Millera (x = długość, y w „stopniach”)."""
    lat = max(-89.5, min(89.5, lat))
    y = 1.25 * math.log(math.tan(math.pi / 4 + 0.4 * math.radians(lat)))
    return lon, math.degrees(y)


def project_ring(coords):
    pts = list(coords)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    out = []
    for lon, lat in pts:
        x, y = miller(lon, lat)
        p = (round(x, 3), round(y, 3))
        if not out or out[-1] != p:
            out.append(p)
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def polygon_to_data(poly):
    rings = [project_ring(poly.exterior.coords)]
    rings += [project_ring(i.coords) for i in poly.interiors]
    rings = [r for r in rings if len(r) >= 3]
    if not rings:
        return None
    verts = np.array([p for r in rings for p in r], dtype=np.float64)
    ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
    tri = earcut.triangulate_float64(verts, ends)
    if len(tri) == 0:
        return None
    return {
        "rings": [[c for p in r for c in p] for r in rings],
        "tri": [int(i) for i in tri],
    }


def main():
    local = os.path.join(HERE, "ne_50m_admin_0_countries.geojson")
    if os.path.exists(local):
        with open(local, encoding="utf-8") as f:
            src = json.load(f)
    else:
        print("Pobieram dane Natural Earth…")
        with urllib.request.urlopen(URL) as r:
            src = json.loads(r.read().decode("utf-8"))

    countries = []
    for feat in src["features"]:
        p = feat["properties"]
        code = p["ADM0_A3"]
        full = shape(feat["geometry"])
        # powierzchnia w km² (odwzorowanie sinusoidalne jest równopolowe)
        area_km2 = transform(
            lambda x, y: (x * math.cos(math.radians(y)) * KM_PER_DEG,
                          y * KM_PER_DEG), full).area
        geom = full.simplify(TOLERANCE, preserve_topology=True)
        polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
        out_polys = [d for d in (polygon_to_data(pl) for pl in polys
                                 if not pl.is_empty) if d]
        if not out_polys:
            continue
        lx, ly = miller(p["LABEL_X"], p["LABEL_Y"])
        countries.append({
            "id": code,
            "name": NAME_OVERRIDES.get(code) or p.get("NAME_PL") or p["NAME"],
            "continent": p["CONTINENT"],
            "sovereign": p["TYPE"] in ("Sovereign country", "Country"),
            "color": int(p.get("MAPCOLOR7") or 1),
            "area": round(area_km2),
            "label": [round(lx, 3), round(ly, 3)],
            "polys": out_polys,
        })

    countries.sort(key=lambda c: c["id"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"source": "Natural Earth 1:50m (public domain)",
                   "projection": "miller",
                   "countries": countries}, f, ensure_ascii=False,
                  separators=(",", ":"))
    print(f"Zapisano {len(countries)} obszarów do {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
