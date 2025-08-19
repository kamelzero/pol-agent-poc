# PoL-Agent-PoC — Multi-Domain Pattern-of-Life with Sim + Agents

Goal: Multi-agent PoL demo for AIS/ADS-B/Ground with Kafka+TimescaleDB, agents, and Streamlit UI.

## Quickstart

1. Copy `.env.example` to `.env` and adjust as needed.
2. Start infra only: `docker compose up -d zookeeper kafka db`
3. Initialize DB schema: `make db-init`
4. Start everything in containers (bridges, normalizers, agents, UI): `docker compose up -d --build`
5. UI is at http://localhost:8501

## Layout
See spec in repo and README sections; packages contain common schemas, bridges, normalizers, agents, and UI.

## Data flow

- Bridges (synthetic publishers) → Kafka raw topics
  - `packages/bridges/ais_bridge.py` → `ais.raw`
  - `packages/bridges/adsb_bridge.py` → `adsb.raw`
  - `packages/bridges/ground_bridge.py` → `ground.raw`
- Normalizers (Kafka consumers) → DB tables + normalized topics
  - `packages/normalizers/ais_normalizer.py`: `ais.raw` → write `tracks_ais` and publish `ais.norm`
  - `packages/normalizers/adsb_normalizer.py`: `adsb.raw` → write `tracks_adsb` and publish `adsb.norm`
  - `packages/normalizers/ground_normalizer.py`: `ground.raw` → write `tracks_ground` and publish `ground.norm`
- Domain agents (Kafka consumers) → domain anomalies
  - `packages/agents/maritime_agent.py`: `ais.norm` → detect loiter/rendezvous → publish `pol.anomalies.domain` and write `anomalies_domain`
  - `packages/agents/air_agent.py`: `adsb.norm` → detect holding → publish `pol.anomalies.domain` and write `anomalies_domain`
  - `packages/agents/ground_agent.py`: `ground.norm` → detect convoy → publish `pol.anomalies.domain` and write `anomalies_domain`
- Fusion agent (Kafka consumer) → fused anomalies
  - `packages/agents/fusion_agent.py`: `pol.anomalies.domain` → cluster by H3+minute → publish `pol.anomalies.fused` and write `anomalies_fused`
- LLM explainer (optional)
  - `packages/agents/explainer_agent.py`: `pol.anomalies.domain` → generate summary/triage → publish `pol.anomalies.explained` and write `anomalies_explained`

### LLM explainer configuration

- By default the explainer uses a deterministic fallback (no external calls).
- To enable OpenAI calls, set these env vars (host shell or Compose):
  - `OPENAI_API_KEY`: your API key
  - `LLM_PROVIDER`: `openai` (default)
  - `LLM_MODEL`: e.g., `gpt-4o-mini` (default)
  - `LLM_TEMPERATURE`: default `0.2`
  - `LLM_MAX_TOKENS`: default `256`

Compose already passes `OPENAI_API_KEY` through to `agent-explainer` if set in your environment:

```bash
export OPENAI_API_KEY=sk-...
docker compose up -d --build agent-explainer
```

To smoke test the LLM path (skips if no key):

```bash
python -m pytest -q -k llm
```
- UI (Streamlit) → DB queries
  - `packages/ui/app.py` queries `tracks_*`, `anomalies_*` and visualizes

## Kafka topics

- Raw: `ais.raw`, `adsb.raw`, `ground.raw`
- Normalized: `ais.norm`, `adsb.norm`, `ground.norm`
- Domain anomalies: `pol.anomalies.domain`
- Fused anomalies: `pol.anomalies.fused`
- Explained anomalies: `pol.anomalies.explained`

## Monitoring Kafka

From host (using kcat):

```bash
kcat -b localhost:29092 -L                       # list metadata
kcat -b localhost:29092 -t ais.raw -C -o -5 -q   # last 5 AIS raw messages
kcat -b localhost:29092 -t pol.anomalies.domain -C -o -10 -q
```

From inside the Kafka container (Confluent tools):

```bash
docker compose exec kafka kafka-topics --bootstrap-server kafka:9092 --list
docker compose exec kafka kafka-console-consumer \
  --bootstrap-server kafka:9092 --topic ais.raw --from-beginning --max-messages 5
```

Note: host processes should use `localhost:29092`; containers use `kafka:9092`.

## BlueSky integration (ADS-B via .scn)

- Install BlueSky into the venv:

```bash
make bluesky-install
```

- Clone upstream to access bundled `.scn` examples (optional, for scenarios only):

```bash
make bluesky-git-clone
# scenarios now under external/bluesky/scenario/*.scn
```

- Run BlueSky → Kafka bridge with a scenario:

```bash
make up && make db-init
BLUESKY_SCN=/home/ubuntu/pol-agent-poc/external/bluesky/scenario/demo.scn \
BLUESKY_PUBLISH_HZ=1 BLUESKY_DT_MULT=1.0 make bluesky-bridge
```

- Verify messages:

```bash
kcat -b localhost:29092 -t adsb.raw -C -o -5 -q
```

### Troubleshooting with kcat

- Install on Ubuntu:

```bash
sudo apt-get update && sudo apt-get install -y kafkacat || sudo apt-get install -y kcat
```

- List metadata and peek messages:

```bash
kcat -b localhost:29092 -L
kcat -b localhost:29092 -t adsb.raw -C -o -5 -q
kcat -b localhost:29092 -t adsb.norm -C -o -5 -q
kcat -b localhost:29092 -t pol.anomalies.domain -C -o -10 -q
```

- Common issues:
- If no `adsb.raw` messages: ensure the bridge is running and `BLUESKY_SCN` points to a valid `.scn`.
- If normalizers/agents not producing: run `make norms` and `make agents`.
- If permissions error on Docker socket: add your user to `docker` group and re-login (`newgrp docker`).

## Database schema

Tables are created by `ops/sql/ddl.sql` into TimescaleDB:

- Tracks: `tracks_ais`, `tracks_adsb`, `tracks_ground`
- Anomalies: `anomalies_domain`, `anomalies_fused`

Quick inspection examples:

```bash
docker compose exec -it db psql -U postgres -d pol
```

Inside psql:

```sql
\dt
SELECT COUNT(*) FROM anomalies_domain;
SELECT ts, domain, type, entity_id, score FROM anomalies_domain ORDER BY ts DESC LIMIT 10;
```

## Parameters and how to adjust them

- Environment variables (set in shell or `.env`):
  - `KAFKA_BROKER` (default `localhost:29092`): host/port for Kafka
  - `SCENARIO_ID` (default `demo-aug16`): tag added to all envelopes
  - `H3_RES` (default `8`): H3 resolution for spatial indexing
  - `POSTGRES_HOST`/`POSTGRES_PORT`/`POSTGRES_DB`/`POSTGRES_PASSWORD`: DB connection (UI/normalizers)

- Synthetic volume and behavior (edit these files):
  - Entity counts: `seeds` in
    - `packages/bridges/ais_bridge.py`
    - `packages/bridges/adsb_bridge.py`
    - `packages/bridges/ground_bridge.py`
  - Emit rate: `time.sleep(1)` in each bridge `main()` controls ~1 Hz
  - Motion/behavior randomness: see `simulate_*` functions in the same files

- Historical backfill (manual injection to raw topics):
  - `packages/bridges/backfill.py`
  - Callable functions with minute windows:
    - `backfill_ais(minutes=15)` (includes loiterer)
    - `backfill_adsb(minutes=10)` (includes holding pattern)
    - `backfill_ground(minutes=5)` (includes 3-vehicle convoy)

Examples:

```bash
PYTHONPATH=packages python packages/bridges/backfill.py
PYTHONPATH=packages python -c "from bridges.backfill import backfill_ais; backfill_ais(30)"
```

- Detection thresholds (agent heuristics):
  - Maritime `packages/agents/maritime_agent.py`
    - `LOITER_SPEED_KTS`, `RENDEZ_RADIUS_M`, `WIN_SEC` (10 min window)
  - Air `packages/agents/air_agent.py`
    - `MAX_RADIUS_M`, `MAX_MEAN_SPEED_KTS`, `MIN_CUM_HEADING_DEG`, `WIN_SEC` (8 min window)
  - Ground `packages/agents/ground_agent.py`
    - `NEIGHBOR_RADIUS_M`, `MAX_SPEED_DIFF_MPS`, `MAX_DIST_STD_M`, `MIN_GROUP`, `WIN_SEC`

## Agents architecture and orchestration

- Framework: plain Python with `kafka-python` consumers/producers and Pydantic models. No Faust/streaming framework is used in this PoC to keep it simple and transparent.
- Orchestrator: none (by design for the PoC). Processes are started via `make` targets. This keeps deployment simple and avoids extra infra.
- Rationale: the goal is a lightweight, hackable demo. If needed, you can later:
  - Wrap each component as a containerized service and supervise with systemd/Kubernetes
  - Adopt a stream processor (Faust, Flink) for richer stateful processing
  - Add a workflow orchestrator (Airflow/Prefect) for scheduled backfills and batch tasks

## Useful commands

```bash
# Infra
make up && make db-init   # host-mode
docker compose up -d      # containerized mode

# Kafka peek (host)
kcat -b localhost:29092 -t ais.raw -C -o -3 -q
kcat -b localhost:29092 -t pol.anomalies.domain -C -o -5 -q

# DB quick checks
docker compose exec -T db psql -U postgres -d pol -c "SELECT COUNT(*) FROM tracks_ais;"
docker compose exec -T db psql -U postgres -d pol -c "SELECT ts, domain, type, entity_id, score FROM anomalies_domain ORDER BY ts DESC LIMIT 10;"
docker compose exec -T db psql -U postgres -d pol -c "SELECT ts, domain, type, summary, triage, model FROM anomalies_explained ORDER BY ts DESC LIMIT 10;"
```
