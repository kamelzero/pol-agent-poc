import hashlib
import json
import os
from datetime import UTC, datetime

from kafka import KafkaConsumer, KafkaProducer
from normalizers.db_writer import ExplainedWriter

IN_TOPIC = "pol.anomalies.domain"
OUT_TOPIC = "pol.anomalies.explained"


def now_utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def _make_prompt(dom: dict) -> str:
    return (
        "Summarize the following anomaly and suggest a short triage action.\n"
        f"Domain: {dom.get('domain')}\n"
        f"Type: {dom.get('type')}\n"
        f"Entity: {dom.get('entity_id')}\n"
        f"Evidence: {json.dumps(dom.get('evidence', {}), separators=(',', ':'))}\n"
    )


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _call_llm(prompt: str) -> tuple[str, str]:
    # Placeholder: integrate OpenAI or another provider via env configuration
    # If OPENAI_API_KEY is set, you could call the API here. For now, deterministic fallback.
    summary = "Anomaly detected based on provided heuristics."
    triage = "Log and monitor. If persistent or high-risk, escalate to operator."
    model = os.getenv("LLM_MODEL", "fallback")
    return summary, triage, model


def explainer_agent():
    broker = os.getenv("KAFKA_BROKER", "localhost:29092")
    c = KafkaConsumer(
        IN_TOPIC,
        bootstrap_servers=broker,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="latest",
        enable_auto_commit=True,
    )
    p = KafkaProducer(bootstrap_servers=broker, value_serializer=lambda v: json.dumps(v).encode("utf-8"))
    writer = ExplainedWriter()

    while True:
        msg = next(c)
        dom = msg.value
        prompt = _make_prompt(dom)
        summary, triage, model = _call_llm(prompt)
        out = {
            "ts": now_utc_iso(),
            "domain": dom.get("domain"),
            "entity_id": dom.get("entity_id"),
            "h3": dom.get("h3"),
            "type": dom.get("type"),
            "score": dom.get("score"),
            "summary": summary,
            "triage": triage,
            "model": model,
            "prompt_hash": _hash(prompt),
        }
        p.send(OUT_TOPIC, out)
        writer.write(out)


if __name__ == "__main__":
    explainer_agent()
