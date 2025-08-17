import json
import os
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from kafka import KafkaConsumer, KafkaProducer
from normalizers.db_writer import FusedWriter


IN_TOPIC = "pol.anomalies.domain"
OUT_TOPIC = "pol.anomalies.fused"

WIN_SEC = 5 * 60


def now_utc() -> datetime:
    return datetime.now(UTC)


def minute_bucket(ts_iso: str) -> str:
    dt = datetime.fromisoformat(ts_iso)
    dt = dt.replace(second=0, microsecond=0)
    return dt.isoformat()


def fusion_agent():
    broker = os.getenv("KAFKA_BROKER", "localhost:29092")
    c = KafkaConsumer(
        IN_TOPIC,
        bootstrap_servers=broker,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="latest",
        enable_auto_commit=True,
    )
    p = KafkaProducer(
        bootstrap_servers=broker,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    # Keep a short window of domain anomalies
    buf: deque[dict] = deque(maxlen=5_000)
    writer = FusedWriter("anomalies_fused")

    while True:
        msg = next(c)
        dom = msg.value
        buf.append(dom)

        # Evict old
        cutoff = now_utc() - timedelta(seconds=WIN_SEC)
        while buf and datetime.fromisoformat(buf[0]["ts"]) < cutoff:
            buf.popleft()

        # Simple cluster: same h3 cell and same minute bucket
        clusters: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for a in buf:
            key = (a.get("h3"), minute_bucket(a.get("ts")))
            clusters[key].append(a)

        for (h3_cell, min_bucket), items in clusters.items():
            if not items:
                continue
            # Require at least 2 domains to create a fused anomaly
            domains = sorted({it.get("domain") for it in items})
            if len(domains) < 2:
                continue
            entities = sorted({it.get("entity_id") for it in items})
            types = sorted({it.get("type") for it in items})
            cluster_id = f"{h3_cell}|{min_bucket}"
            confidence = min(0.95, 0.5 + 0.1 * len(items))
            fused = {
                "ts": items[-1]["ts"],
                "cluster_id": cluster_id,
                "types": types,
                "h3_center": h3_cell,
                "entities": entities,
                "confidence": confidence,
                "evidence_links": [],
            }
            p.send(OUT_TOPIC, fused)
            writer.write(fused)


if __name__ == "__main__":
    fusion_agent()


