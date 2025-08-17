import math
import os
import random
import time

from bridges.bridge_base import SCENARIO_ID, producer, ts_now
from common.geo import latlon_to_h3
from common.pol_schemas import Envelope

random.seed(2024)
H3_RES = int(os.getenv("H3_RES", "8"))
TOPIC = "ground.raw"


def simulate_vehicle(vid: str, lat: float, lon: float, mps: float, heading: float):
    while True:
        # grid-like motion with occasional turns
        if random.random() < 0.1:
            heading += random.choice([90, -90, 0])
        mps = max(0.5, mps * random.uniform(0.95, 1.05))
        # convert m/s to a small degree delta (~111km per deg)
        meters_per_deg = 111_000
        dlat = (mps / meters_per_deg) * math.cos(math.radians(heading))
        dlon = (mps / (meters_per_deg * math.cos(math.radians(max(min(lat, 89.9), -89.9))))) * math.sin(
            math.radians(heading)
        )
        lat += dlat
        lon += dlon
        yield vid, lat, lon, mps, heading


def main():
    p = producer()
    seeds = [(f"VEH{i:05d}", 34.05 + (i % 3) * 0.01, -118.25 - (i // 3) * 0.01, 8.0, 0.0) for i in range(6)]
    gens = [simulate_vehicle(*s) for s in seeds]
    while True:
        for g in gens:
            vid, lat, lon, spd, hdg = next(g)
            msg = Envelope(
                scenario_id=SCENARIO_ID,
                source="ground",
                ts=ts_now(),
                entity_id=vid,
                lat=lat,
                lon=lon,
                speed=spd,
                course=hdg,
                attrs={"type": "car"},
                h3=latlon_to_h3(lat, lon, H3_RES),
            ).model_dump()
            p.send(TOPIC, msg)
        time.sleep(1)


if __name__ == "__main__":
    main()
