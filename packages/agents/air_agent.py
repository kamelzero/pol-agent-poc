import json
import os
from collections import defaultdict, deque
from datetime import UTC, datetime

from common.pol_schemas import DomainAnomaly, Envelope
from normalizers.db_writer import AnomaliesWriter
from kafka import KafkaConsumer, KafkaProducer

IN_TOPIC = "adsb.norm"
OUT_TOPIC = "pol.anomalies.domain"

WIN_SEC = 8 * 60
MAX_RADIUS_M = 3000
MAX_MEAN_SPEED_KTS = 120.0
MIN_CUM_HEADING_DEG = 720

def now_utc(): return datetime.now(UTC)

def haversine_m(lat1, lon1, lat2, lon2):
    import math
    R=6371000
    p1,p2 = math.radians(lat1),math.radians(lat2)
    dphi = math.radians(lat2-lat1)
    dl = math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(min(1, math.sqrt(a)))

def ang_delta(a, b):
    d = (a - b + 540.0) % 360.0 - 180.0
    return d

def air_agent():
    broker = os.getenv("KAFKA_BROKER", "localhost:29092")
    c = KafkaConsumer(IN_TOPIC, bootstrap_servers=broker,
                      value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                      auto_offset_reset="latest", enable_auto_commit=True)
    p = KafkaProducer(bootstrap_servers=broker,
                      value_serializer=lambda v: json.dumps(v).encode("utf-8"))

    buf: dict[str, deque] = defaultdict(lambda: deque(maxlen=600))

    writer = AnomaliesWriter("anomalies_domain")

    while True:
        msg = next(c)
        env = Envelope(**msg.value)
        buf[env.entity_id].append(env)

        series = [e for e in buf[env.entity_id] if (now_utc() - datetime.fromisoformat(e.ts)).total_seconds() <= WIN_SEC]
        if len(series) < 60:
            continue

        mean_speed = sum((e.speed or 0.0) for e in series) / len(series)
        if mean_speed >= MAX_MEAN_SPEED_KTS:
            continue

        lat_c = sum(e.lat for e in series) / len(series)
        lon_c = sum(e.lon for e in series) / len(series)
        rmax = max(haversine_m(lat_c, lon_c, e.lat, e.lon) for e in series)
        if rmax > MAX_RADIUS_M:
            continue

        headings = [e.course or 0.0 for e in series]
        cum = 0.0
        for i in range(1, len(headings)):
            cum += abs(ang_delta(headings[i], headings[i-1]))
        if cum < MIN_CUM_HEADING_DEG:
            continue

        anomaly = DomainAnomaly(
            ts=series[-1].ts, domain="air", entity_id=env.entity_id, h3=series[-1].h3,
            type="holding", score=0.75,
            evidence={"mean_speed_kts": round(mean_speed,1), "radius_m": int(rmax), "cum_heading_deg": int(cum)}
        )
        doc = anomaly.model_dump()
        p.send(OUT_TOPIC, doc)
        writer.write(doc)

if __name__ == "__main__":
    air_agent()
