import json
import os
from datetime import UTC, datetime

from dotenv import load_dotenv
from kafka import KafkaProducer

load_dotenv()

# When running services on the host with Docker Compose, the externally exposed
# Kafka listener is on localhost:29092 (see compose.yaml). Allow override via env.
BROKER = os.getenv("KAFKA_BROKER", "localhost:29092")
SCENARIO_ID = os.getenv("SCENARIO_ID", "demo-aug16")

def ts_now():
    return datetime.now(UTC).isoformat()

def producer():
    return KafkaProducer(bootstrap_servers=BROKER,
                         value_serializer=lambda v: json.dumps(v).encode("utf-8"))
