import json
import os

from dotenv import load_dotenv
from kafka import KafkaConsumer, KafkaProducer

load_dotenv()

# Match docker-compose advertised external listener
BROKER = os.getenv("KAFKA_BROKER", "localhost:29092")

def make_consumer(topic):
    return KafkaConsumer(topic, bootstrap_servers=BROKER,
                         value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                         auto_offset_reset="latest", enable_auto_commit=True)

def make_producer():
    return KafkaProducer(bootstrap_servers=BROKER,
                         value_serializer=lambda v: json.dumps(v).encode("utf-8"))
