import json

import h3
from shapely.geometry import Point, shape


def latlon_to_h3(lat: float, lon: float, res: int) -> str:
    # h3 v4 API uses latlng_to_cell
    return h3.latlng_to_cell(lat, lon, res)

def point_in_any_polygon(lat: float, lon: float, geojson_path: str) -> bool:
    with open(geojson_path) as f:
        gj = json.load(f)
    p = Point(lon, lat)
    return any(shape(feat["geometry"]).contains(p) for feat in gj["features"])
