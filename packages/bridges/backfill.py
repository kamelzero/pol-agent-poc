import math
import os
import random
from datetime import UTC, datetime, timedelta

from bridges.bridge_base import SCENARIO_ID, producer
from common.geo import latlon_to_h3
from common.pol_schemas import Envelope

H3_RES = int(os.getenv("H3_RES", "8"))


def iso_at(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def backfill_ais(minutes: int = 15):
    p = producer()
    now = datetime.now(UTC)
    # 4 normal + 1 loitering slow mover to trigger loiter
    seeds = [
        (f"MMSI{100000000 + i}", 34.0 + i * 0.01, -119.0 - i * 0.01, 8.0, 270.0) for i in range(4)
    ]
    seeds.append(("MMSI999999999", 34.25, -119.25, 1.0, 0.0))  # loiter candidate

    steps = minutes * 60
    for t in range(steps):
        ts = iso_at(now - timedelta(seconds=steps - t))
        for mmsi, lat, lon, knots, heading in list(seeds):
            # small random walk; very low speed for loiter entity maintained
            if knots > 1.5 and random.random() < 0.02:
                knots = max(0.2, knots * random.uniform(0.7, 1.05))
            heading = (heading + random.uniform(-2, 2)) % 360
            dlat = (knots * 0.0003) * math.cos(math.radians(heading))
            dlon = (knots * 0.0003) * math.sin(math.radians(heading))
            lat += dlat
            lon += dlon
            msg = Envelope(
                scenario_id=SCENARIO_ID,
                source="ais",
                ts=ts,
                entity_id=mmsi,
                lat=lat,
                lon=lon,
                speed=knots,
                course=heading,
                attrs={"type": "cargo"},
                h3=latlon_to_h3(lat, lon, H3_RES),
            ).model_dump()
            p.send("ais.raw", msg)
        # update seeds with new state
        seeds = [
            (m, msg["lat"], msg["lon"], k, h)
            for (m, _, _, k, h), msg in zip(seeds, [], strict=False)
        ]  # placeholder to satisfy structure


def backfill_adsb(minutes: int = 10):
    p = producer()
    now = datetime.now(UTC)
    # 4 normal cruisers + 1 holding pattern (low speed ~10 kts with heading wrap)
    seeds = [
        (f"ICAO{i:06X}", 34.3 + i * 0.02, -118.9 - i * 0.02, 220.0, 90.0, 12000.0 + i * 500)
        for i in range(4)
    ]
    seeds.append(("ICAOHOLD", 34.5, -118.5, 10.0, 0.0, 9000.0))  # holding candidate

    steps = minutes * 60
    latlons = {icao: (lat, lon) for icao, lat, lon, *_ in seeds}
    headings = {icao: hdg for icao, *_, hdg, _ in seeds}
    speeds = {icao: spd for icao, *_, spd, _, _ in seeds}
    alts = {icao: alt for icao, *_, alt in seeds}

    for t in range(steps):
        ts = iso_at(now - timedelta(seconds=steps - t))
        for icao in list(latlons.keys()):
            lat, lon = latlons[icao]
            spd = speeds[icao]
            hdg = headings[icao]
            alt = alts[icao]
            if icao == "ICAOHOLD":
                hdg = (hdg + 10.0) % 360  # wrap headings
                spd = 10.0
            else:
                if random.random() < 0.03:
                    alt += random.uniform(-200, 200)
                hdg = (hdg + random.uniform(-3, 3)) % 360
            dlat = (spd * 0.0008) * math.cos(math.radians(hdg))
            dlon = (spd * 0.0008) * math.sin(math.radians(hdg))
            lat += dlat
            lon += dlon
            latlons[icao] = (lat, lon)
            headings[icao] = hdg
            alts[icao] = alt
            msg = Envelope(
                scenario_id=SCENARIO_ID,
                source="adsb",
                ts=ts,
                entity_id=icao,
                lat=lat,
                lon=lon,
                speed=spd,
                course=hdg,
                alt=alt,
                attrs={"aircraft": "A320"},
                h3=latlon_to_h3(lat, lon, H3_RES),
            ).model_dump()
            p.send("adsb.raw", msg)


def backfill_ground(minutes: int = 5):
    p = producer()
    now = datetime.now(UTC)
    # 3 convoy vehicles close together + 3 normal
    seeds = [
        ("VEHCONV1", 34.05, -118.25, 7.5, 0.0),
        ("VEHCONV2", 34.0502, -118.2501, 7.6, 0.0),
        ("VEHCONV3", 34.0504, -118.2502, 7.4, 0.0),
        ("VEH10001", 34.08, -118.28, 8.0, 90.0),
        ("VEH10002", 34.06, -118.22, 9.0, 270.0),
        ("VEH10003", 34.04, -118.26, 8.5, 180.0),
    ]
    steps = minutes * 60
    for t in range(steps):
        ts = iso_at(now - timedelta(seconds=steps - t))
        new = []
        for vid, lat, lon, mps, hdg in seeds:
            if vid.startswith("VEHCONV"):
                hdg = 0.0  # move north together
            else:
                if random.random() < 0.1:
                    hdg = (hdg + random.choice([90, -90, 0])) % 360
            meters_per_deg = 111_000
            dlat = (mps / meters_per_deg) * math.cos(math.radians(hdg))
            dlon = (
                mps
                / (meters_per_deg * max(0.2, math.cos(math.radians(max(min(lat, 89.9), -89.9)))))
            ) * math.sin(math.radians(hdg))
            lat += dlat
            lon += dlon
            new.append((vid, lat, lon, mps, hdg))
            msg = Envelope(
                scenario_id=SCENARIO_ID,
                source="ground",
                ts=ts,
                entity_id=vid,
                lat=lat,
                lon=lon,
                speed=mps,
                course=hdg,
                attrs={"type": "car"},
                h3=latlon_to_h3(lat, lon, H3_RES),
            ).model_dump()
            p.send("ground.raw", msg)
        seeds = new


def main():
    random.seed(123)
    backfill_ais(15)
    backfill_adsb(10)
    backfill_ground(5)


if __name__ == "__main__":
    main()
