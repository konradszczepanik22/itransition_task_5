from datetime import datetime
from io import BytesIO
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from analysis import SERIES_COLOR, TEST_STYLE, TOTAL, TREND_COLOR

NAVY = colors.HexColor("#1F2A44")
STRIPE = colors.HexColor("#EEF1F6")
GRID = colors.HexColor("#BFC6D4")
WIDTH = A4[0] - 4 * cm
MAX_EPISODES = 60
base = getSampleStyleSheet()
STYLES = {
    "title": ParagraphStyle("title", parent=base["Title"], fontSize=24, textColor=NAVY, spaceAfter=6),
    "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontSize=12, alignment=TA_CENTER,
                               textColor=colors.grey),
    "h1": ParagraphStyle("h1", parent=base["Heading1"], textColor=NAVY, spaceBefore=6),
    "h2": ParagraphStyle("h2", parent=base["Heading2"], textColor=NAVY),
    "body": base["BodyText"],
    "small": ParagraphStyle("small", parent=base["BodyText"], fontSize=8, textColor=colors.grey),
}
def fmt(value):
    return f"{value:,.2f}"
def table(rows, widths=None, header=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    commands = [
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, STRIPE]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    else:
        commands += [("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("ALIGN", (1, 0), (-1, -1), "LEFT")]
    t.setStyle(TableStyle(commands))
    return t
def frame_rows(df, index_name):
    return [[index_name, *df.columns]] + [
        [str(i), *(fmt(v) if isinstance(v, float) else str(v) for v in row)] for i, row in df.iterrows()
    ]
def figure(width=17, height=6.5):
    fig, ax = plt.subplots(figsize=(width / 2.54, height / 2.54), dpi=150)
    ax.grid(alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.tick_params(labelsize=7)
    return fig, ax
def image(fig, width=WIDTH):
    buf = BytesIO()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    w, h = fig.get_size_inches()
    return Image(buf, width=width, height=width * h / w)
def draw(ax, values, kind, color=SERIES_COLOR, label=None, bottom=None):
    if kind == "line":
        ax.plot(values.index, values, color=color, lw=1.2, label=label)
    else:
        ax.bar(values.index, values, color=color, width=0.85, label=label, bottom=bottom)
def mark(ax, result, window=None):
    flags = result.flags if window is None else result.flags.loc[window]
    for test, (color, marker, _) in TEST_STYLE.items():
        hit = flags.index[flags[test]]
        if len(hit):
            ax.scatter(hit, result.values[hit], color=color, marker=marker, s=28, zorder=5,
                       edgecolor="white", linewidth=0.5, label=test)
def series_chart(result, kind, degree):
    fig, ax = figure()
    draw(ax, result.values, "bar" if kind == "stacked" else kind, label=result.name)
    ax.plot(result.trendline.index, result.trendline, "--", color=TREND_COLOR, lw=1.3,
            label=f"Trend (degree {degree})")
    mark(ax, result)
    ax.legend(fontsize=7, ncol=3, frameon=False)
    return image(fig)
def overview_chart(results, kind):
    fig, ax = figure(height=7.5)
    mines = [r for name, r in results.items() if name != TOTAL]
    palette = plt.get_cmap("tab10")
    bottom = None
    for i, r in enumerate(mines):
        if kind == "line":
            draw(ax, r.values, "line", palette(i), r.name)
        else:
            draw(ax, r.values, "bar", palette(i), r.name, bottom if kind == "stacked" else None)
            bottom = r.values if bottom is None else bottom + r.values
    ax.legend(fontsize=7, ncol=min(len(mines), 5), frameon=False)
    return image(fig)
def episode_chart(result, ep):
    lo, hi = ep.start - pd.Timedelta(days=10), ep.end + pd.Timedelta(days=10)
    window = result.values.loc[lo:hi].index
    fig, ax = figure(width=17, height=5)
    ax.plot(window, result.values[window], color=SERIES_COLOR, lw=1.3, marker="o", ms=2.5)
    ax.axvspan(ep.start - pd.Timedelta(hours=12), ep.end + pd.Timedelta(hours=12), color="#F3A712", alpha=0.18)
    ax.axhline(ep.baseline, color="grey", lw=0.8, ls=":", label="Median")
    mark(ax, result, window)
    ax.legend(fontsize=7, ncol=5, frameon=False)
    return image(fig, WIDTH * 0.85)
def episode_section(result, ep, number):
    rows = [
        ["Series", ep.series],
        ["Type", ep.kind],
        ["Period", f"{ep.start:%Y-%m-%d} to {ep.end:%Y-%m-%d} ({ep.days} day{'s' if ep.days > 1 else ''})"],
        ["Peak", f"{fmt(ep.peak_value)} on {ep.peak_date:%Y-%m-%d}"],
        ["Median of series", fmt(ep.baseline)],
        ["Deviation from median", f"{ep.deviation:+.1f}%"],
        ["Detected by", ", ".join(ep.tests)],
    ]
    return KeepTogether([
        Paragraph(f"{number}. {ep.kind} in {ep.series}, {ep.start:%Y-%m-%d}", STYLES["h2"]),
        table(rows, [5 * cm, WIDTH - 5 * cm], header=False),
        Spacer(1, 4),
        episode_chart(result, ep),
        Spacer(1, 10),
    ])
def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(2 * cm, 1.2 * cm, "Weyland-Yutani Corporation  |  Mining output analysis")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {doc.page}")
    canvas.restoreState()
def build_pdf(wide, results, summary_df, counts, params, degree, kind):
    episodes = sorted((ep for r in results.values() for ep in r.episodes), key=lambda e: -abs(e.deviation))
    shown = episodes[:MAX_EPISODES]
    settings = [
        ["Period", f"{wide.index.min():%Y-%m-%d} to {wide.index.max():%Y-%m-%d} ({len(wide)} days)"],
        ["Mines", ", ".join(c for c in wide.columns if c != TOTAL)],
        ["IQR rule", f"k = {params.iqr_k}"],
        ["Z-score", f"|z| > {params.z_threshold}"],
        ["Moving average", f"window {params.ma_window} days, distance > {params.ma_percent}%"],
        ["Grubbs' test", f"alpha = {params.grubbs_alpha} (iterative, two-sided)"],
        ["Trendline", f"polynomial of degree {degree}"],
        ["Detected anomalies", f"{len(episodes)} episodes"],
    ]
    story = [
        Spacer(1, 3 * cm),
        Paragraph("Mining Output Analysis", STYLES["title"]),
        Paragraph(f"Weyland-Yutani Corporation  |  generated {datetime.now():%Y-%m-%d %H:%M}", STYLES["subtitle"]),
        Spacer(1, 1.2 * cm),
        table(settings, [5 * cm, WIDTH - 5 * cm], header=False),
        Spacer(1, 0.8 * cm),
        Paragraph("Daily output by mine", STYLES["h2"]),
        overview_chart(results, kind),
        PageBreak(),
        Paragraph("1. Summary statistics", STYLES["h1"]),
        table(frame_rows(summary_df, "Series")),
        Spacer(1, 12),
        Paragraph("2. Anomalies detected per test (days)", STYLES["h1"]),
        table(frame_rows(counts, "Series")),
        PageBreak(),
        Paragraph("3. Series charts", STYLES["h1"]),
        Paragraph("Markers show days flagged by each test; the dashed line is the fitted trend.", STYLES["small"]),
    ]
    for r in results.values():
        story.append(KeepTogether([Paragraph(r.name, STYLES["h2"]), series_chart(r, kind, degree)]))
    story += [PageBreak(), Paragraph("4. Anomaly details", STYLES["h1"])]
    if len(episodes) > len(shown):
        story.append(Paragraph(
            f"Showing the {len(shown)} largest of {len(episodes)} episodes, ordered by deviation.", STYLES["small"]))
    if not episodes:
        story.append(Paragraph("No anomalies were detected with the current parameters.", STYLES["body"]))
    story += [episode_section(results[ep.series], ep, i) for i, ep in enumerate(shown, 1)]

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm,
                            bottomMargin=2 * cm, title="Mining Output Analysis", author="Weyland-Yutani Corporation")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()