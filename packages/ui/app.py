import os

import pandas as pd
import psycopg
import pydeck as pdk
import streamlit as st

DB_DSN = f"host={os.getenv('POSTGRES_HOST','localhost')} port={os.getenv('POSTGRES_PORT','5432')} dbname={os.getenv('POSTGRES_DB','pol')} user=postgres password={os.getenv('POSTGRES_PASSWORD','postgres')}"

st.set_page_config(layout="wide", page_title="PoL Agent Demo")
st.title("🌊 PoL Agent Demo — Multi-domain")

with st.sidebar:
    st.header("Filters")
    score_thr = st.slider("Score >=", 0.0, 1.0, 0.6, 0.05)
    domain_sel = st.multiselect(
        "Domains", ["maritime", "air", "ground"], default=["maritime", "air", "ground"]
    )
    type_sel = st.multiselect(
        "Types",
        ["loiter", "rendezvous", "holding", "convoy"],
        default=["loiter", "rendezvous", "holding", "convoy"],
    )


@st.cache_data(ttl=5)
def fetch_tracks(table, limit=5000):
    with psycopg.connect(DB_DSN) as conn:
        q = f"SELECT ts, lat, lon, speed, course FROM {table} ORDER BY ts DESC LIMIT {limit}"
        return pd.read_sql(q, conn)


@st.cache_data(ttl=3)
def fetch_anomalies():
    with psycopg.connect(DB_DSN) as conn:
        dom = pd.read_sql("SELECT * FROM anomalies_domain ORDER BY ts DESC LIMIT 500", conn)
        fus = pd.read_sql("SELECT * FROM anomalies_fused ORDER BY ts DESC LIMIT 200", conn)
        return dom, fus


tabs = st.tabs(["Map", "Anomalies", "Fused"])

with tabs[0]:
    ais = fetch_tracks("tracks_ais")
    adsb = fetch_tracks("tracks_adsb")
    ground = fetch_tracks("tracks_ground")
    st.subheader("Tracks (recent)")
    layers = []
    for df, _name in [(ais, "AIS"), (adsb, "ADSB"), (ground, "GROUND")]:
        if not df.empty:
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=df,
                    get_position="[lon, lat]",
                    get_radius=80,
                    pickable=True,
                )
            )
    deck = pdk.Deck(
        map_style=None,
        initial_view_state=pdk.ViewState(latitude=34, longitude=-119, zoom=8),
        layers=layers,
    )
    st.pydeck_chart(deck)

with tabs[1]:
    dom, _ = fetch_anomalies()
    if not dom.empty:
        dom = dom[dom["score"] >= score_thr]
        dom = dom[dom["domain"].isin(domain_sel)]
        dom = dom[dom["type"].isin(type_sel)]
    st.subheader("Domain anomalies (filtered)")
    st.dataframe(dom)
    if not dom.empty:
        opts = [
            f"{row.ts} | {row.domain}.{row.type} | {row.entity_id}" for _, row in dom.iterrows()
        ]
        choice = st.selectbox("Inspect evidence", opts)
        idx = opts.index(choice) if choice in opts else None
        if idx is not None:
            row = dom.iloc[idx]
            try:
                st.json(row["evidence"])
            except Exception:
                import json as _json

                st.json(_json.loads(row["evidence"]))

with tabs[2]:
    _, fus = fetch_anomalies()
    st.dataframe(fus)
