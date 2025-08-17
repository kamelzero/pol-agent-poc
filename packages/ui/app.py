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
    domain_sel = st.multiselect("Domains", ["maritime", "air", "ground"], default=["maritime", "air", "ground"])
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


tabs = st.tabs(["Map", "Anomalies", "Fused", "Metrics"])

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
        opts = [f"{row.ts} | {row.domain}.{row.type} | {row.entity_id}" for _, row in dom.iterrows()]
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

with tabs[3]:
    st.subheader("Metrics — counts over time")
    with psycopg.connect(DB_DSN) as conn:
        # Bucket by minute for recent 2 hours
        q_tracks = (
            "SELECT date_trunc('minute', ts) as minute, 'ais' as src, count(*) as cnt FROM tracks_ais "
            "WHERE ts > now() - interval '2 hours' GROUP BY 1 "
            "UNION ALL "
            "SELECT date_trunc('minute', ts) as minute, 'adsb' as src, count(*) as cnt FROM tracks_adsb "
            "WHERE ts > now() - interval '2 hours' GROUP BY 1 "
            "UNION ALL "
            "SELECT date_trunc('minute', ts) as minute, 'ground' as src, count(*) as cnt FROM tracks_ground "
            "WHERE ts > now() - interval '2 hours' GROUP BY 1 "
            "ORDER BY 1, 2"
        )
        tracks = pd.read_sql(q_tracks, conn)

        q_dom = (
            "SELECT date_trunc('minute', ts) as minute, type, count(*) as cnt FROM anomalies_domain "
            "WHERE ts > now() - interval '2 hours' GROUP BY 1,2 ORDER BY 1,2"
        )
        dom = pd.read_sql(q_dom, conn)

        q_fused = (
            "SELECT date_trunc('minute', ts) as minute, count(*) as cnt FROM anomalies_fused "
            "WHERE ts > now() - interval '2 hours' GROUP BY 1 ORDER BY 1"
        )
        fused = pd.read_sql(q_fused, conn)

        if not tracks.empty:
            st.markdown("Tracks per minute (by source)")
            pivot = tracks.pivot_table(index="minute", columns="src", values="cnt", fill_value=0)
            st.line_chart(pivot)

        if not dom.empty:
            st.markdown("Domain anomalies per minute (by type)")
            pivot_a = dom.pivot_table(index="minute", columns="type", values="cnt", fill_value=0)
            st.area_chart(pivot_a)

        if not fused.empty:
            st.markdown("Fused anomalies per minute")
            fused = fused.set_index("minute").sort_index()
            st.bar_chart(fused)

    st.divider()
    st.subheader("Snapshot totals")
    with psycopg.connect(DB_DSN) as conn:
        totals = pd.read_sql(
            "SELECT 'tracks_ais' t, count(*) FROM tracks_ais "
            "UNION ALL SELECT 'tracks_adsb', count(*) FROM tracks_adsb "
            "UNION ALL SELECT 'tracks_ground', count(*) FROM tracks_ground "
            "UNION ALL SELECT 'anomalies_domain', count(*) FROM anomalies_domain "
            "UNION ALL SELECT 'anomalies_fused', count(*) FROM anomalies_fused",
            conn,
        )
    st.dataframe(totals)
