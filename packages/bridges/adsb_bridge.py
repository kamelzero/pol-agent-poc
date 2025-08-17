import math
import os
import random
import time

from bridges.bridge_base import SCENARIO_ID, producer, ts_now
from common.geo import latlon_to_h3
from common.pol_schemas import Envelope

random.seed(1337)
H3_RES = int(os.getenv("H3_RES", "8"))
TOPIC = "adsb.raw"

def simulate_aircraft(icao: str, lat: float, lon: float, kts: float, heading: float, alt_ft: float):
    while True:
        if random.random() < 0.05:
            # small altitude change
            alt_ft += random.uniform(-200, 200)
        if random.random() < 0.02:
            # slight slow down / turn
            kts = max(80.0, kts * random.uniform(0.8, 1.05))
            heading += random.uniform(-3, 3)
        dlat = (kts * 0.0008) * math.cos(math.radians(heading))
        dlon = (kts * 0.0008) * math.sin(math.radians(heading))
        lat += dlat
        lon += dlon
        yield icao, lat, lon, kts, heading, alt_ft

def main():
    p = producer()
    seeds = [(f"ICAO{i:06X}", 34.3 + i*0.02, -118.9 - i*0.02, 220.0, 90.0, 12000+ i*500) for i in range(5)]
    gens = [simulate_aircraft(*s) for s in seeds]
    while True:
        for g in gens:
            icao, lat, lon, spd, hdg, alt = next(g)
            msg = Envelope(
                scenario_id=SCENARIO_ID, source="adsb", ts=ts_now(),
                entity_id=icao, lat=lat, lon=lon, speed=spd, course=hdg, alt=alt,
                attrs={"aircraft":"A320"},
                h3=latlon_to_h3(lat, lon, H3_RES)
            ).model_dump()
            p.send(TOPIC, msg)
        time.sleep(1)

if __name__ == "__main__":
    main()
