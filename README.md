# PoL-Agent-PoC — Multi-Domain Pattern-of-Life with Sim + Agents

Goal: Multi-agent PoL demo for AIS/ADS-B/Ground with Kafka+TimescaleDB, agents, and Streamlit UI.

## Quickstart

1. Copy `.env.example` to `.env` and adjust as needed.
2. Start infra: `docker compose up -d`
3. Initialize DB schema: `make db-init`
4. In one terminal: `make bridges`
5. In another: `make norms`
6. In another: `make agents`
7. Launch UI: `make ui`

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
- UI (Streamlit) → DB queries
  - `packages/ui/app.py` queries `tracks_*`, `anomalies_*` and visualizes

## Kafka topics

- Raw: `ais.raw`, `adsb.raw`, `ground.raw`
- Normalized: `ais.norm`, `adsb.norm`, `ground.norm`
- Domain anomalies: `pol.anomalies.domain`
- Fused anomalies: `pol.anomalies.fused`

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
make up && make db-init

# Start pipelines
make bridges
make norms
make agents

# UI
make ui

# Kafka peek (host)
kcat -b localhost:29092 -t ais.raw -C -o -3 -q
kcat -b localhost:29092 -t pol.anomalies.domain -C -o -5 -q

# DB quick checks
docker compose exec -T db psql -U postgres -d pol -c "SELECT COUNT(*) FROM tracks_ais;"
docker compose exec -T db psql -U postgres -d pol -c "SELECT ts, domain, type, entity_id, score FROM anomalies_domain ORDER BY ts DESC LIMIT 10;"
```
