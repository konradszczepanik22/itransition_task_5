import re
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from scipy import stats

TOTAL = "Total"
SHEET_ID = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)")
@dataclass(frozen=True)
class TestParams:
    iqr_k: float = 1.5
    z_threshold: float = 3.0
    ma_window: int = 7
    ma_percent: float = 40.0
    grubbs_alpha: float = 0.05
@dataclass
class Episode:
    series: str
    start: pd.Timestamp
    end: pd.Timestamp
    kind: str
    peak_date: pd.Timestamp
    peak_value: float
    baseline: float
    tests: list = field(default_factory=list)
    @property
    def days(self):
        return (self.end - self.start).days + 1
    @property
    def deviation(self):
        return (self.peak_value - self.baseline) / self.baseline * 100 if self.baseline else 0.0
def csv_url(source):
    match = SHEET_ID.search(source)
    if not match:
        return source
    return f"https://docs.google.com/spreadsheets/d/{match[1]}/gviz/tq?tqx=out:csv&sheet=Data"
def load(source):
    raw = pd.read_csv(csv_url(source.strip()), dtype=str)
    raw = raw.iloc[:, :3]
    raw.columns = ["date", "mine", "output"]
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
    number = raw["output"].str.replace("[\\s\u00a0\u202f]", "", regex=True).str.replace(",", ".")
    raw["output"] = pd.to_numeric(number, errors="coerce")
    raw["mine"] = raw["mine"].astype("string").str.strip()
    data = raw.dropna().query("mine != ''")
    wide = data.pivot_table(index="date", columns="mine", values="output", aggfunc="sum", sort=False)
    wide = wide[list(dict.fromkeys(data["mine"]))].sort_index()
    wide[TOTAL] = wide.sum(axis=1)
    return wide
def summary(wide):
    q1, q3 = wide.quantile(0.25), wide.quantile(0.75)
    return pd.DataFrame({
        "Mean": wide.mean(),
        "Std dev": wide.std(),
        "Median": wide.median(),
        "Q1": q1,
        "Q3": q3,
        "IQR": q3 - q1,
        "Min": wide.min(),
        "Max": wide.max(),
    })
def iqr(s, p):
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    spread = p.iqr_k * (q3 - q1)
    return (s < q1 - spread) | (s > q3 + spread)
def zscore(s, p):
    sd = s.std()
    return (s - s.mean()).abs() / sd > p.z_threshold if sd else pd.Series(False, index=s.index)
def moving_average(s, p):
    ma = s.rolling(p.ma_window, min_periods=p.ma_window).mean().shift(1)
    return ((s - ma).abs() / ma * 100 > p.ma_percent).fillna(False)
def grubbs(s, p):
    flags = pd.Series(False, index=s.index)
    rest = s.copy()
    while len(rest) > 2:
        n = len(rest)
        sd = rest.std()
        if not sd:
            break
        dev = (rest - rest.mean()).abs()
        t = stats.t.ppf(1 - p.grubbs_alpha / (2 * n), n - 2)
        critical = (n - 1) / np.sqrt(n) * np.sqrt(t ** 2 / (n - 2 + t ** 2))
        if dev.max() / sd <= critical:
            break
        flags[dev.idxmax()] = True
        rest = rest.drop(dev.idxmax())
    return flags
TESTS = {"IQR rule": iqr, "Z-score": zscore, "Moving average": moving_average, "Grubbs": grubbs}
def detect(s, p):
    return pd.DataFrame({name: test(s, p) for name, test in TESTS.items()})
def trend(s, degree):
    x = np.arange(len(s))
    return pd.Series(np.polyval(np.polyfit(x, s.to_numpy(), degree), x), index=s.index)
def episodes(name, s, flags):
    hit = flags.any(axis=1)
    baseline = s.median()
    runs = (hit != hit.shift()).cumsum()[hit]
    found = []
    for _, idx in runs.groupby(runs).groups.items():
        part = s.loc[idx]
        peak = (part - baseline).abs().idxmax()
        found.append(Episode(
            series=name,
            start=idx.min(),
            end=idx.max(),
            kind="Spike" if part[peak] > baseline else "Drop",
            peak_date=peak,
            peak_value=float(part[peak]),
            baseline=float(baseline),
            tests=[t for t in flags.columns if flags.loc[idx, t].any()],
        ))
    return found
@dataclass
class SeriesResult:
    name: str
    values: pd.Series
    flags: pd.DataFrame
    trendline: pd.Series
    episodes: list
def analyse(wide, params, degree):
    results = {}
    for name in wide.columns:
        s = wide[name]
        flags = detect(s, params)
        results[name] = SeriesResult(name, s, flags, trend(s, degree), episodes(name, s, flags))
    return results
def anomaly_counts(results):
    return pd.DataFrame({name: r.flags.sum() for name, r in results.items()}).T
TEST_STYLE = {
    "IQR rule": ("#E4572E", "o", "circle"),
    "Z-score": ("#7B2CBF", "s", "square"),
    "Moving average": ("#F3A712", "^", "triangle-up"),
    "Grubbs": ("#17BEBB", "D", "diamond"),
}
SERIES_COLOR = "#2E5AAC"
TREND_COLOR = "#C1121F"