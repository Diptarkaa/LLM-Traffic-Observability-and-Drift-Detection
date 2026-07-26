from __future__ import annotations

import streamlit as st

from db import summary_stats

st.set_page_config(page_title="Agentic Protection - Drift Dashboard", layout="wide")

st.title("Agentic Protection: Drift Dashboard")
st.caption(
    "Semantic drift detection over the 7-day synthetic capture dataset. "
    "Use the pages in the sidebar to explore topic clusters, the anomaly "
    "timeline, and drill into individual sessions."
)

stats = summary_stats()

col1, col2, col3 = st.columns(3)
col1.metric("Total captured events", f"{stats['total_events']:,}")
col2.metric("Distinct sessions", f"{stats['total_sessions']:,}")
col3.metric("Flagged drift sessions", f"{stats['total_flagged']:,}")

col4, col5 = st.columns(2)
col4.metric("Last baseline computed", str(stats["last_baseline"]) if stats["last_baseline"] else "not yet run")
col5.metric("Last detection pass", str(stats["last_detection"]) if stats["last_detection"] else "not yet run")

if stats["total_flagged"] == 0:
    st.warning(
        "No drift events flagged yet. If you just started the stack, the "
        "detector runs once on startup and every ~30s after — refresh in a "
        "moment. If this persists, check `docker compose logs detector`."
    )
else:
    st.success(
        f"{stats['total_flagged']} session(s) flagged as drift so far. "
        "Head to **Anomaly Timeline** to see them, or **Session Drill-down** "
        "to inspect one directly."
    )

st.divider()
st.markdown(
    """
    ### Pages
    - **1 Topic Clusters** — UMAP projection of prompt embeddings, colored by
      unsupervised k-means cluster (precomputed and cached — see `db.py`).
    - **2 Anomaly Timeline** — drift events detected over the 7-day window,
      with click-through to the offending session.
    - **3 Session Drill-down** — full turn-by-turn transcript for a single
      session, with its per-turn distance-from-baseline trend.
    """
)
