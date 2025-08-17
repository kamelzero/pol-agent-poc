import json
import os
from collections import defaultdict, deque
from datetime import UTC, datetime
from itertools import combinations

from common.pol_schemas import DomainAnomaly, Envelope
from normalizers.db_writer import AnomaliesWriter
from kafka import KafkaConsumer, KafkaProducer

IN_TOPIC = "ground.norm"
OUT_TOPIC = "pol.anomalies.domain"

WIN_SEC = 3 * 60
NEIGHBOR_RADIUS_M = 200
MAX_DIST_STD_M = 50
MAX_SPEED_DIFF_MPS = 1.0
MIN_GROUP = 3

def now_utc(): return datetime.now(UTC)

def haversine_m(lat1, lon1, lat2, lon2):
    import math
    R=6371000
    p1,p2 = math.radians(lat1),math.radians(lat2)
    dphi = math.radians(lat2-lat1)
    dl = math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(min(1, math.sqrt(a)))

def ground_agent():
    broker = os.getenv("KAFKA_BROKER", "localhost:29092")
    c = KafkaConsumer(IN_TOPIC, bootstrap_servers=broker,
                      value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                      auto_offset_reset="latest", enable_auto_commit=True)
    p = KafkaProducer(bootstrap_servers=broker,
                      value_serializer=lambda v: json.dumps(v).encode("utf-8"))

    buf: dict[str, deque] = defaultdict(lambda: deque(maxlen=400))
    last_emit: dict[str, str] = {}

    writer = AnomaliesWriter("anomalies_domain")

    while True:
        msg = next(c)
        env = Envelope(**msg.value)
        buf[env.entity_id].append(env)

        recent_last = {}
        for eid, q in list(buf.items()):
            series = [e for e in q if (now_utc() - datetime.fromisoformat(e.ts)).total_seconds() <= WIN_SEC]
            if series:
                buf[eid] = deque(series, maxlen=400)
                recent_last[eid] = series[-1]
            else:
                buf.pop(eid, None)

        ids = list(recent_last.keys())
        if len(ids) < MIN_GROUP:
            continue

        groups = []
        for i in range(len(ids)):
            seed = ids[i]
            members = [seed]
            for j in range(len(ids)):
                if j == i: continue
                other = ids[j]
                a, b = recent_last[seed], recent_last[other]
                d = haversine_m(a.lat, a.lon, b.lat, b.lon)
                if d <= NEIGHBOR_RADIUS_M and abs((a.speed or 0.0) - (b.speed or 0.0)) <= MAX_SPEED_DIFF_MPS:
                    members.append(other)
            members = sorted(set(members))
            if len(members) >= MIN_GROUP:
                groups.append(members)

        uniq = {}
        for g in groups:
            key = "|".join(sorted(g))
            uniq[key] = sorted(g)

        for key, members in uniq.items():
            pts = [recent_last[m] for m in members]
            dists = []
            for a,b in combinations(pts, 2):
                dists.append(haversine_m(a.lat, a.lon, b.lat, b.lon))
            if not dists:
                continue
            mean_d = sum(dists)/len(dists)
            var = sum((x-mean_d)**2 for x in dists)/len(dists)
            std = var ** 0.5
            if std <= MAX_DIST_STD_M:
                last_ts = last_emit.get(key)
                if last_ts and (now_utc() - datetime.fromisoformat(last_ts)).total_seconds() < 60:
                    continue
                last_emit[key] = pts[-1].ts
                anomaly = DomainAnomaly(
                    ts=pts[-1].ts, domain="ground", entity_id=key, h3=pts[-1].h3,
                    type="convoy", score=0.8,
                    evidence={"size": len(members), "dist_std_m": int(std)}
                )
                doc = anomaly.model_dump()
                p.send(OUT_TOPIC, doc)
                writer.write(doc)

if __name__ == "__main__":
    ground_agent()
