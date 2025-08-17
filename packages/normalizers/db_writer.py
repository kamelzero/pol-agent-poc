import os

from common.pol_schemas import Envelope
from dotenv import load_dotenv
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB

load_dotenv()

DB_URL = f"postgresql+psycopg://postgres:{os.getenv('POSTGRES_PASSWORD','postgres')}@{os.getenv('POSTGRES_HOST','localhost')}:{os.getenv('POSTGRES_PORT','5432')}/{os.getenv('POSTGRES_DB','pol')}"
engine = create_engine(DB_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)


class TracksWriter:
    def __init__(self, table: str):
        self.table = table
        # Some tables (e.g., ADS-B) include alt; AIS and ground do not
        includes_alt = table.endswith("adsb")
        if includes_alt:
            base = text(
                f"""
                INSERT INTO {table} (ts, scenario_id, entity_id, lat, lon, speed, course, alt, h3, attrs)
                VALUES (:ts, :scenario_id, :entity_id, :lat, :lon, :speed, :course, :alt, :h3, :attrs)
                """
            )
        else:
            base = text(
                f"""
                INSERT INTO {table} (ts, scenario_id, entity_id, lat, lon, speed, course, h3, attrs)
                VALUES (:ts, :scenario_id, :entity_id, :lat, :lon, :speed, :course, :h3, :attrs)
                """
            )
        # Ensure attrs is treated as JSONB
        self.stmt = base.bindparams(bindparam("attrs", type_=JSONB))
        self.includes_alt = includes_alt

    def write_envelope(self, env: Envelope):
        with engine.begin() as conn:
            params = {
                "ts": env.ts,
                "scenario_id": env.scenario_id,
                "entity_id": env.entity_id,
                "lat": env.lat,
                "lon": env.lon,
                "speed": env.speed,
                "course": env.course,
                "h3": env.h3,
                "attrs": json_dumps(env.attrs),
            }
            if self.includes_alt:
                params["alt"] = env.alt
            conn.execute(self.stmt, params)


class AnomaliesWriter:
    def __init__(self, table: str = "anomalies_domain"):
        self.table = table
        self.stmt = text(
            f"""
            INSERT INTO {table} (ts, domain, entity_id, h3, type, score, evidence)
            VALUES (:ts, :domain, :entity_id, :h3, :type, :score, :evidence)
            """
        ).bindparams(bindparam("evidence", type_=JSONB))

    def write(self, anomaly: dict):
        with engine.begin() as conn:
            conn.execute(
                self.stmt,
                {
                    "ts": anomaly["ts"],
                    "domain": anomaly.get("domain"),
                    "entity_id": anomaly.get("entity_id"),
                    "h3": anomaly.get("h3"),
                    "type": anomaly.get("type"),
                    "score": anomaly.get("score"),
                    "evidence": json_dumps(anomaly.get("evidence", {})),
                },
            )


class FusedWriter:
    def __init__(self, table: str = "anomalies_fused"):
        self.table = table
        self.stmt = text(
            f"""
            INSERT INTO {table} (ts, cluster_id, types, h3_center, entities, confidence, evidence_links)
            VALUES (:ts, :cluster_id, :types, :h3_center, :entities, :confidence, :evidence_links)
            """
        )

    def write(self, fused: dict):
        with engine.begin() as conn:
            conn.execute(
                self.stmt,
                {
                    "ts": fused["ts"],
                    "cluster_id": fused.get("cluster_id"),
                    "types": fused.get("types", []),
                    "h3_center": fused.get("h3_center"),
                    "entities": fused.get("entities", []),
                    "confidence": fused.get("confidence", 0.5),
                    "evidence_links": fused.get("evidence_links", []),
                },
            )


def json_dumps(d):  # already a dict; return as-is for JSONB binding
    return d
