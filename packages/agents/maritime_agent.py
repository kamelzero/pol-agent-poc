import json
import os
from collections import defaultdict, deque
from datetime import UTC, datetime

from common.pol_schemas import DomainAnomaly, Envelope
from kafka import KafkaConsumer, KafkaProducer
from normalizers.db_writer import AnomaliesWriter

IN_TOPIC = "ais.norm"
OUT_TOPIC = "pol.anomalies.domain"

WIN_SEC = 60 * 10
LOITER_SPEED_KTS = 2.0
RENDEZ_RADIUS_M = 800
RENDEZ_MIN_MIN = 15


def now_utc():
    return datetime.now(UTC)


def haversine_m(lat1, lon1, lat2, lon2):
    import math

    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1, math.sqrt(a)))


def maritime_agent():
    broker = os.getenv("KAFKA_BROKER", "localhost:29092")
    c = KafkaConsumer(
        IN_TOPIC,
        bootstrap_servers=broker,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="latest",
        enable_auto_commit=True,
    )
    p = KafkaProducer(bootstrap_servers=broker, value_serializer=lambda v: json.dumps(v).encode("utf-8"))

    buf: dict[str, deque] = defaultdict(lambda: deque(maxlen=600))  # ~10 min @ 1Hz

    writer = AnomaliesWriter("anomalies_domain")

    while True:
        msg = next(c)
        env = Envelope(**msg.value)
        buf[env.entity_id].append(env)

        series = list(buf[env.entity_id])
        if len(series) > 60:
            speeds = [e.speed or 0.0 for e in series]
            dur_min = len(series) / 60
            if max(speeds) <= LOITER_SPEED_KTS and dur_min >= 10:
                anomaly = DomainAnomaly(
                    ts=series[-1].ts,
                    domain="maritime",
                    entity_id=env.entity_id,
                    h3=env.h3,
                    type="loiter",
                    score=0.7,
                    evidence={"duration_min": round(dur_min, 1), "speed_max": max(speeds)},
                )
                doc = anomaly.model_dump()
                p.send(OUT_TOPIC, doc)
                writer.write(doc)

        recent = {
            eid: list(q)
            for eid, q in buf.items()
            if q and (now_utc() - datetime.fromisoformat(q[-1].ts)).total_seconds() < WIN_SEC
        }
        last_points = [(eid, q[-1]) for eid, q in recent.items()]
        for i in range(len(last_points)):
            for j in range(i + 1, len(last_points)):
                ei, li = last_points[i]
                ej, lj = last_points[j]
                if (li.speed or 0) <= LOITER_SPEED_KTS and (lj.speed or 0) <= LOITER_SPEED_KTS:
                    d = haversine_m(li.lat, li.lon, lj.lat, lj.lon)
                    if d <= RENDEZ_RADIUS_M:
                        anomaly = DomainAnomaly(
                            ts=li.ts,
                            domain="maritime",
                            entity_id=f"{ei}|{ej}",
                            h3=li.h3,
                            type="rendezvous",
                            score=0.8,
                            evidence={"distance_m": int(d)},
                        )
                        doc = anomaly.model_dump()
                        p.send(OUT_TOPIC, doc)
                        writer.write(doc)


if __name__ == "__main__":
    maritime_agent()
