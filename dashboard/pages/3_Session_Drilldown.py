from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from db import fetch_all_session_ids, fetch_baseline, fetch_drift_events, fetch_session_turns
from distance import nearest_cluster_distance

st.set_page_config(page_title="Session Drill-down", layout="wide")
st.title("Session Drill-down")
st.caption("Full turn-by-turn transcript for a single session, with its per-turn distance-from-baseline trend.")

flagged = fetch_drift_events()
all_sessions = fetch_all_session_ids()

if not all_sessions:
    st.warning("No sessions found yet.")
    st.stop()

default_session = st.session_state.get("selected_session_id")
if default_session is None and not flagged.empty:
    default_session = flagged.sort_values("distance", ascending=False).iloc[0]["session_id"]
if default_session is None:
    default_session = all_sessions[0]

options = sorted(set(all_sessions) | {default_session})
default_index = options.index(default_session) if default_session in options else 0

session_id = st.selectbox("Session", options=options, index=default_index)
st.session_state["selected_session_id"] = session_id

flag_row = flagged[flagged["session_id"] == session_id]
if not flag_row.empty:
    row = flag_row.iloc[0]
    st.error(
        f"**Flagged as drift** (caught by: {row['flagged_by']}) — "
        f"distance={row['distance']:.4f} (threshold={row['threshold']:.4f}), "
        f"cohort={row['cohort']}, worst turn: `{row['worst_request_id']}`"
    )
else:
    st.success("Not flagged by the detector.")

turns = fetch_session_turns(session_id)
if turns.empty:
    st.warning("No turns found for this session.")
    st.stop()

route = turns["route"].iloc[0]
baseline = fetch_baseline(route)

st.subheader("Distance from baseline, per turn")
if baseline is None:
    st.info("No baseline computed yet for this route — the detector's baseline job hasn't run.")
else:
    prompt_turns = turns[turns["frame_type"] == "request_body"].reset_index(drop=True)
    distances = []
    for _, t in prompt_turns.iterrows():
        if t["prompt_embedding"] is None:
            distances.append(None)
            continue
        vec = np.array(t["prompt_embedding"], dtype=np.float64)
        distances.append(nearest_cluster_distance(vec, baseline["clusters"]))

    trend_df = pd.DataFrame(
        {
            "turn_index": range(len(prompt_turns)),
            "distance": distances,
            "event_ts": prompt_turns["event_ts"],
            "prompt_preview": prompt_turns["prompt_text"].str.slice(0, 80),
        }
    )
    fig = px.line(
        trend_df, x="turn_index", y="distance", markers=True,
        hover_data=["prompt_preview", "event_ts"],
        title="Per-turn distance from baseline centroid (the pivot, if any, shows up as a jump)",
    )
    fig.add_hline(y=baseline["threshold"], line_dash="dash", line_color="red", annotation_text="threshold")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Transcript")
for _, turn in turns.iterrows():
    if turn["frame_type"] == "request_body" and turn["prompt_text"]:
        with st.chat_message("user"):
            st.markdown(turn["prompt_text"])
            st.caption(f"{turn['event_ts']} · request_id={turn['request_id']}")
    elif turn["frame_type"] == "response_body" and turn["completion_text"]:
        with st.chat_message("assistant"):
            st.markdown(turn["completion_text"])
            st.caption(f"{turn['event_ts']} · request_id={turn['request_id']}")
