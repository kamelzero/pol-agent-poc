import math
import os
import random
import time

from bridges.bridge_base import SCENARIO_ID, producer, ts_now
from common.geo import latlon_to_h3
from common.pol_schemas import Envelope

H3_RES = int(os.getenv("H3_RES", "8"))
TOPIC = "ais.raw"


def simulate_track(mmsi: str, lat: float, lon: float, knots: float, heading: float):
    while True:
        if random.random() < 0.02:
            knots = max(0.2, knots * random.uniform(0.2, 0.5))
        heading += random.uniform(-2, 2)
        dlat = (knots * 0.0003) * math.cos(math.radians(heading))
        dlon = (knots * 0.0003) * math.sin(math.radians(heading))
        lat += dlat
        lon += dlon
        yield mmsi, lat, lon, knots, heading


def main():
    p = producer()
    seeds = [("MMSI" + str(100000000 + i), 34.0 + i * 0.01, -119.0 - i * 0.01, 8.0, 270.0) for i in range(5)]
    gens = [simulate_track(*s) for s in seeds]
    while True:
        for g in gens:
            mmsi, lat, lon, sog, cog = next(g)
            msg = Envelope(
                scenario_id=SCENARIO_ID,
                source="ais",
                ts=ts_now(),
                entity_id=mmsi,
                lat=lat,
                lon=lon,
                speed=sog,
                course=cog,
                attrs={"type": "tanker" if "2" in mmsi else "cargo"},
                h3=latlon_to_h3(lat, lon, H3_RES),
            ).model_dump()
            p.send(TOPIC, msg)
        time.sleep(1)


if __name__ == "__main__":
    main()
