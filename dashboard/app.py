import os
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from analysis import (
    SERIES_COLOR,
    TEST_STYLE,
    TOTAL,
    TREND_COLOR,
    TestParams,
    analyse,
    anomaly_counts,
    load,
    summary,
)
from report import build_pdf

st.set_page_config(page_title="Mining Output Analytics", layout="wide")
st.markdown(
    """
    <style>
    [data-testid="stMetric"] {
        background: var(--secondary-background-color);
        border-radius: 10px;
        padding: 12px 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
def default_source():
    try:
        return st.secrets["SHEET_URL"]
    except (KeyError, FileNotFoundError):
        return os.environ.get("SHEET_URL", "")
@st.cache_data(ttl=300, show_spinner="Loading data from the generator…")
def fetch(source):
    return load(source)
def sidebar():
    sb = st.sidebar
    sb.header("Data source")
    source = sb.text_input("Google Sheets link", default_source(), help="Link to the generator spreadsheet")
    if sb.button("Refresh data", width="stretch"):
        fetch.clear()
        st.session_state.pop("pdf", None)
    sb.header("Anomaly tests")
    params = TestParams(
        iqr_k=sb.slider("IQR rule: k", 0.5, 4.0, 1.5, 0.1),
        z_threshold=sb.slider("Z-score: threshold", 1.0, 5.0, 3.0, 0.1),
        ma_window=sb.slider("Moving average: window (days)", 3, 30, 7),
        ma_percent=sb.slider("Moving average: max distance (%)", 5, 100, 40),
        grubbs_alpha=sb.select_slider("Grubbs: significance", [0.001, 0.005, 0.01, 0.025, 0.05, 0.1], 0.05),
    )
    sb.header("Charts")
    kind = sb.radio("Chart type", ["line", "bar", "stacked"], horizontal=True)
    degree = sb.select_slider("Trendline degree", [1, 2, 3, 4], 2)
    return source, params, kind, degree
def base_layout(fig, height=420):
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.08, x=0),
        xaxis_title=None,
        yaxis_title="Output",
    )
    return fig
def overview_figure(results, kind):
    fig = go.Figure()
    for name, r in results.items():
        if name == TOTAL:
            continue
        trace = go.Scatter(mode="lines") if kind == "line" else go.Bar()
        fig.add_trace(trace.update(x=r.values.index, y=r.values, name=name))
    fig.update_layout(barmode="stack" if kind == "stacked" else "group", bargap=0.1)
    return base_layout(fig, 460)
def series_figure(r, kind, degree):
    main = go.Scatter(mode="lines", line=dict(color=SERIES_COLOR)) if kind == "line" else go.Bar(
        marker_color=SERIES_COLOR)
    fig = go.Figure(main.update(x=r.values.index, y=r.values, name=r.name))
    fig.add_trace(go.Scatter(x=r.trendline.index, y=r.trendline, mode="lines", name=f"Trend (degree {degree})",
                             line=dict(color=TREND_COLOR, dash="dash")))
    for test, (color, _, symbol) in TEST_STYLE.items():
        hit = r.flags.index[r.flags[test]]
        fig.add_trace(go.Scatter(x=hit, y=r.values[hit], mode="markers", name=test,
                                 marker=dict(color=color, symbol=symbol, size=10,
                                             line=dict(color="white", width=1))))
    return base_layout(fig)
def episodes_frame(r):
    return pd.DataFrame([{
        "Type": e.kind,
        "Start": e.start.date(),
        "End": e.end.date(),
        "Days": e.days,
        "Peak": e.peak_value,
        "Deviation %": e.deviation,
        "Tests": ", ".join(e.tests),
    } for e in r.episodes])
def report_button(wide, results, stats, counts, params, degree, kind):
    if st.button("Generate PDF report", type="primary"):
        with st.spinner("Building the report…"):
            st.session_state.pdf = build_pdf(wide, results, stats, counts, params, degree, kind)
    if "pdf" in st.session_state:
        st.download_button("Download PDF", st.session_state.pdf, "mining_report.pdf", "application/pdf")
def main():
    source, params, kind, degree = sidebar()
    st.title("Mining Output Analytics")
    st.caption("Weyland-Yutani Corporation  |  daily output from the generator spreadsheet")
    if not source:
        st.info("Paste the link to the generator spreadsheet in the sidebar.")
        return
    try:
        wide = fetch(source)
    except Exception as exc:
        st.error(f"Could not load data: {exc}")
        return
    results = analyse(wide, params, degree)
    stats = summary(wide)
    counts = anomaly_counts(results)
    mines = [c for c in wide.columns if c != TOTAL]
    cols = st.columns(4)
    cols[0].metric("Mines", len(mines))
    cols[1].metric("Days", len(wide))
    cols[2].metric("Mean daily total", f"{stats.loc[TOTAL, 'Mean']:,.1f}")
    cols[3].metric("Anomaly episodes", sum(len(r.episodes) for r in results.values()))
    report_button(wide, results, stats, counts, params, degree, kind)
    st.subheader("Daily output by mine")
    st.plotly_chart(overview_figure(results, kind), width="stretch")
    left, right = st.columns([3, 2])
    left.subheader("Statistics")
    left.dataframe(stats.style.format("{:,.2f}"), width="stretch")
    right.subheader("Anomalous days per test")
    right.dataframe(counts, width="stretch")
    st.subheader("Series detail")
    for tab, name in zip(st.tabs([TOTAL, *mines]), [TOTAL, *mines]):
        r = results[name]
        with tab:
            st.plotly_chart(series_figure(r, kind, degree), width="stretch")
            if r.episodes:
                st.dataframe(episodes_frame(r).style.format({"Peak": "{:,.2f}", "Deviation %": "{:+.1f}%"}), width="stretch",
                             hide_index=True)
            else:
                st.caption("No anomalies detected with the current parameters.")
main()