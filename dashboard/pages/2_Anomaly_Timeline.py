from __future__ import annotations

import plotly.express as px
import streamlit as st

from db import fetch_drift_events

st.set_page_config(page_title="Anomaly Timeline", layout="wide")
st.title("Anomaly Timeline")
st.caption(
    "Sessions flagged by the online scoring job: worst per-turn distance "
    "from that route's baseline, plotted over the 7-day capture window. "
    "Points above the dashed threshold line are flagged drift events."
)

df = fetch_drift_events()

if df.empty:
    st.warning(
        "No drift events yet. The detector runs once on startup and every "
        "~30s after — if the stack just started, give it a moment and "
        "refresh this page."
    )
    st.stop()

fig = px.scatter(
    df,
    x="worst_event_ts",
    y="distance",
    color="cohort",
    symbol="flagged_by",
    hover_data={"session_id": True, "worst_prompt_text": True, "turn_count": True, "flagged_by": True},
    title=f"{len(df):,} flagged session(s)",
    height=500,
)
threshold = float(df["threshold"].iloc[0])
fig.add_hline(y=threshold, line_dash="dash", line_color="red", annotation_text="threshold")
st.caption(
    "Points below the threshold line but still flagged got caught by matching a "
    "previously confirmed drift example (`flagged_by = memory`), not by looking "
    "statistically unusual on its own."
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Flagged sessions")
st.caption("Click a row to drill into that session.")

display_df = df[
    ["session_id", "cohort", "route", "distance", "threshold", "turn_count",
     "flagged_by", "worst_event_ts", "worst_prompt_text"]
].sort_values("distance", ascending=False)

event = st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

selected_rows = event.selection.rows if event and event.selection else []
if selected_rows:
    selected_session = display_df.iloc[selected_rows[0]]["session_id"]
    st.session_state["selected_session_id"] = selected_session
    st.success(f"Selected session `{selected_session}`.")
    if st.button("Open in Session Drill-down ->", type="primary"):
        st.switch_page("pages/3_Session_Drilldown.py")
