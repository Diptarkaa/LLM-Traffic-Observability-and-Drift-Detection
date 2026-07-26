from __future__ import annotations

import plotly.express as px
import streamlit as st

from db import ensure_projections_ready, fetch_projections

st.set_page_config(page_title="Topic Clusters", layout="wide")
st.title("Topic Clusters")
st.caption(
    "UMAP projection of prompt embeddings, colored by unsupervised k-means "
    "cluster. Computed once and cached in Postgres (`prompt_projections`) — "
    "UMAP over thousands of 768-dim vectors is too slow to re-run on every "
    "page load."
)

with st.spinner("Computing UMAP projection (first load only — subsequent loads read from cache)..."):
    was_cached = ensure_projections_ready(n_clusters=8)

if not was_cached:
    st.info("Projection computed and cached just now. Future loads will be instant.")

df = fetch_projections()

if df.empty:
    st.warning("No embeddings found yet. Make sure the consumer has ingested events.")
    st.stop()

color_by = st.radio(
    "Color points by",
    options=["cluster_id", "cohort"],
    horizontal=True,
    help="cluster_id is what the unsupervised model found; cohort is the synthetic dataset's ground truth label.",
)

df_plot = df.copy()
df_plot["cluster_id"] = df_plot["cluster_id"].astype(str)

fig = px.scatter(
    df_plot,
    x="x",
    y="y",
    color=color_by,
    hover_data={"session_id": True, "prompt_preview": True, "x": False, "y": False},
    title=f"{len(df_plot):,} prompts, colored by {color_by}",
    height=650,
)
fig.update_traces(marker=dict(size=6, opacity=0.75))
st.plotly_chart(fig, use_container_width=True)

st.subheader("Cluster composition")
breakdown = (
    df.groupby(["cluster_id", "cohort"]).size().reset_index(name="count").pivot(index="cluster_id", columns="cohort", values="count").fillna(0).astype(int)
)
st.dataframe(breakdown, use_container_width=True)
