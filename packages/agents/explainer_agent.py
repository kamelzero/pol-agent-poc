import hashlib
import json
import os
from datetime import UTC, datetime

from kafka import KafkaConsumer, KafkaProducer
from normalizers.db_writer import ExplainedWriter
from tenacity import retry, stop_after_attempt, wait_exponential

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


@retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=8), stop=stop_after_attempt(3))
def _call_openai(prompt: str, model: str, temperature: float, max_tokens: int) -> tuple[str, str, str]:
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
    sys = (
        "You are a concise triage assistant. Respond with strict JSON containing keys: "
        "summary (short sentence), triage (actionable step), confidence (0-1)."
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(content)
    except Exception:
        data = {"summary": "Auto-triage", "triage": "Monitor.", "confidence": 0.5}
    summary = str(data.get("summary", ""))[:400]
    triage = str(data.get("triage", ""))[:800]
    return summary, triage, model


def _call_llm(prompt: str) -> tuple[str, str, str]:
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "256"))
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        return _call_openai(prompt, model, temperature, max_tokens)
    summary = "Heuristic anomaly; likely benign unless persistent."
    triage = "Monitor for persistence; escalate if repeated or near sensitive zones."
    return summary, triage, "fallback"


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
