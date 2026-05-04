import argparse
import html
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional


CATEGORIES = [
    ("Indices/Futures", ["ES", "SPX", "SPY", "XSP", "NQ", "NDX", "QQQ", "RTY", "RUT", "IWM"]),
    ("Crypto", ["BTC", "ETH"]),
    ("FX", ["EURUSD", "EURCHF", "GBPUSD"]),
    ("Commodities/ETFs", ["GLD", "SLV", "USO", "EWZ"]),
    ("QQQ Top 10", ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "AVGO", "GOOG", "META", "TSLA", "BRK.B"]),
]
MA_NAMES = ["EMA 9", "EMA 20", "SMA 50", "SMA 200", "VWAP"]
MIN_SAMPLE = 20

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "state" / "occurrence_matrix_snapshots"
DEFAULT_REPORT_DIR = ROOT / "reports"
SNAPSHOT_SUFFIX = {"D": "Daily", "W": "Weekly"}


def universe_tickers() -> list[str]:
    tickers: list[str] = []
    for _, category_tickers in CATEGORIES:
        tickers.extend(category_tickers)
    return tickers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a markdown comparison report from TradingView Occurrence Matrix snapshots."
    )
    parser.add_argument("--d", dest="daily_date", help="Daily snapshot date in YYYY-MM-DD format.")
    parser.add_argument("--w", dest="weekly_date", help="Weekly snapshot date in YYYY-MM-DD format.")
    parser.add_argument("--out", dest="out_path", help="Output markdown path.")
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["md", "html", "pdf", "all"],
        default="md",
        help="Output format. Default keeps current markdown-only behavior.",
    )
    parser.add_argument("--chrome", dest="chrome_path", help="Path to chrome.exe or msedge.exe.")
    parser.add_argument(
        "--keep-html",
        action="store_true",
        help="Keep the intermediate HTML file when generating PDF only.",
    )
    return parser.parse_args()


def validate_date_string(value: str) -> str:
    date.fromisoformat(value)
    return value


def discover_latest_snapshot(tf: str) -> Path:
    files = sorted(SNAPSHOT_DIR.glob(f"*_{tf}.json"))
    if not files:
        raise FileNotFoundError(f"No {tf} snapshots found in {SNAPSHOT_DIR}")
    return files[-1]


def snapshot_path_for(date_string: str, tf: str) -> Path:
    return SNAPSHOT_DIR / f"{validate_date_string(date_string)}_{tf}.json"


def load_snapshot(path: Path, expected_tf: str) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Snapshot not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    snapshot_date = raw.get("d")
    snapshot_tf = raw.get("tf")
    ma_values = raw.get("ma")
    data = raw.get("data")

    if not isinstance(snapshot_date, str):
        raise ValueError(f"Snapshot {path} has invalid date field.")
    validate_date_string(snapshot_date)

    if snapshot_tf != expected_tf:
        raise ValueError(f"Snapshot {path} has tf={snapshot_tf!r}; expected {expected_tf!r}.")

    if ma_values != [9, 20, 50, 200, "vwap"]:
        raise ValueError(f"Snapshot {path} has unexpected MA schema: {ma_values!r}")

    if not isinstance(data, dict):
        raise ValueError(f"Snapshot {path} has invalid data field.")

    validate_snapshot_data(path, data)
    return raw


def validate_snapshot_data(path: Path, data: dict) -> None:
    expected = universe_tickers()
    actual = list(data.keys())

    if set(actual) != set(expected):
        missing = [ticker for ticker in expected if ticker not in data]
        extra = [ticker for ticker in actual if ticker not in expected]
        raise ValueError(f"Snapshot {path} ticker mismatch. Missing={missing}; Extra={extra}")

    for ticker in expected:
        values = data[ticker]
        if not isinstance(values, list) or len(values) != len(MA_NAMES) * 4:
            raise ValueError(f"Snapshot {path} ticker {ticker} must have 20 values.")

        for value in values:
            if not isinstance(value, int):
                raise ValueError(f"Snapshot {path} ticker {ticker} has non-integer value: {value!r}")

        for ma_index, ma_name in enumerate(MA_NAMES):
            total, bounce, break_count, false_count = count_block(values, ma_index)
            if bounce + break_count + false_count != total:
                raise ValueError(
                    f"Snapshot {path} ticker {ticker} {ma_name} violates B+Bk+F==T: "
                    f"{bounce}+{break_count}+{false_count}!={total}"
                )


def count_block(values: list[int], ma_index: int) -> tuple[int, int, int, int]:
    start = ma_index * 4
    total = values[start]
    bounce = values[start + 1]
    break_count = values[start + 2]
    false_count = values[start + 3]
    return total, bounce, break_count, false_count


def pct(part: int, total: int) -> int:
    return round(part / total * 100)


def bounce_cell(values: list[int], ma_index: int) -> str:
    total, bounce, _, _ = count_block(values, ma_index)
    if total == 0:
        return "—"
    return f"{pct(bounce, total)}% (n={total})"


def detail_cell(values: list[int], ma_index: int) -> str:
    total, bounce, break_count, false_count = count_block(values, ma_index)
    if total == 0:
        return "—"
    bounce_pct = pct(bounce, total)
    break_pct = pct(break_count, total)
    false_pct = pct(false_count, total)
    return f"{bounce_pct} / {break_pct} / {false_pct} (n={total})"


def best_cell(values: list[int]) -> str:
    best_name = ""
    best_pct = -1

    for ma_index, ma_name in enumerate(MA_NAMES):
        total, bounce, _, _ = count_block(values, ma_index)
        if total < MIN_SAMPLE:
            continue

        bounce_pct = pct(bounce, total)
        if bounce_pct > best_pct:
            best_name = ma_name
            best_pct = bounce_pct

    if best_pct < 0:
        return "—"
    return f"**{best_name}** ({best_pct}%)"


def best_parts(values: list[int]) -> tuple[str, int] | None:
    best_name = ""
    best_pct = -1

    for ma_index, ma_name in enumerate(MA_NAMES):
        total, bounce, _, _ = count_block(values, ma_index)
        if total < MIN_SAMPLE:
            continue

        bounce_pct = pct(bounce, total)
        if bounce_pct > best_pct:
            best_name = ma_name
            best_pct = bounce_pct

    if best_pct < 0:
        return None
    return best_name, best_pct


def render_summary_table(snapshot: dict, category_tickers: list[str]) -> list[str]:
    lines = [
        "| Ticker | EMA 9 | EMA 20 | SMA 50 | SMA 200 | VWAP | Best |",
        "|--------|-------|--------|--------|---------|------|------|",
    ]

    data = snapshot["data"]
    for ticker in category_tickers:
        values = data[ticker]
        cells = [bounce_cell(values, ma_index) for ma_index in range(len(MA_NAMES))]
        lines.append(f"| {ticker} | {' | '.join(cells)} | {best_cell(values)} |")

    return lines


def render_detail_table(snapshot: dict, category_tickers: list[str]) -> list[str]:
    lines = [
        "| Ticker | EMA 9 | EMA 20 | SMA 50 | SMA 200 | VWAP |",
        "|--------|-------|--------|--------|---------|------|",
    ]

    data = snapshot["data"]
    for ticker in category_tickers:
        cells = [detail_cell(data[ticker], ma_index) for ma_index in range(len(MA_NAMES))]
        lines.append(f"| {ticker} | {' | '.join(cells)} |")

    return lines


def render_report(daily_snapshot: dict, weekly_snapshot: dict, latest_date: str) -> str:
    daily_date = daily_snapshot["d"]
    weekly_date = weekly_snapshot["d"]
    total_tickers = len(universe_tickers())

    lines = [
        f"# Occurrence Matrix Report — {latest_date}",
        "",
        f"**Snapshots:** Daily = `{daily_date}` &nbsp;·&nbsp; Weekly = `{weekly_date}`",
        f"**Universe:** {total_tickers} tickers across {len(CATEGORIES)} categories",
        (
            "**Indicator parameters:** Zone Tolerance = 0.1% &nbsp;·&nbsp; "
            f"Lookahead = 2 candles &nbsp;·&nbsp; Min sample (Best) = {MIN_SAMPLE}"
        ),
        f"**MAs evaluated:** {', '.join(MA_NAMES)}",
        "",
        "## How to Read",
        "",
        "- **Bounce%** = % of events where the close returned to the original side (mean reversion).",
        "- **Break%** = % of events where the close persisted on the opposite side for 2 candles (break).",
        "- **False%** = % of events with an intra-bar violation that reverted (noise).",
        "- Bounce% + Break% + False% = 100%.",
        "- **Best** = MA with the highest Bounce% in the row (only MAs with `n ≥ 20`). `—` indicates insufficient sample.",
        "- `n` in parentheses = total events (Bounce + Break + False).",
        "- `—` in a cell = no data (e.g., VWAP on XSP/RUT) or `n < 20`.",
        "",
        "---",
        "",
    ]

    for category_name, tickers in CATEGORIES:
        lines.extend(render_summary_section(category_name, "Daily", daily_snapshot, tickers))
        lines.append("")
        lines.extend(render_summary_section(category_name, "Weekly", weekly_snapshot, tickers))
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## Breakdown — Bounce / Break / False",
            "",
            (
                "Each cell: `B% / Bk% / F% (n)`. Useful to inspect the distribution "
                "(high Break% = firm break-through, high False% = intra-bar noise)."
            ),
            "",
        ]
    )

    for category_name, tickers in CATEGORIES:
        lines.extend(render_detail_section(category_name, "Daily", daily_snapshot, tickers))
        lines.append("")
        lines.extend(render_detail_section(category_name, "Weekly", weekly_snapshot, tickers))
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## Notes",
            "",
            (
                "- **VWAP unavailable on XSP and RUT** — the feed (CBOE:XSP / TVC:RUT) "
                "does not provide VWAP on Daily/Weekly. Marked as `—`."
            ),
            (
                "- **Insufficient sample** (`n < 20`) blocks the entry in the **Best** column "
                "but the percentage is still shown with the `(n=<T>)` suffix."
            ),
            "- **How to regenerate this report:** `python scripts/occurrence_matrix_report.py`",
            "- Raw snapshots: `state/occurrence_matrix_snapshots/`",
            "",
        ]
    )

    return "\n".join(lines)


def heat_class(bounce_pct: int) -> str:
    if bounce_pct < 25:
        return "heat-0"
    if bounce_pct < 35:
        return "heat-1"
    if bounce_pct < 45:
        return "heat-2"
    if bounce_pct < 55:
        return "heat-3"
    if bounce_pct < 65:
        return "heat-4"
    return "heat-5"


def render_html_bounce_cell(values: list[int], ma_index: int) -> str:
    total, bounce, _, _ = count_block(values, ma_index)
    if total == 0:
        return '<td class="ma-cell no-data">—</td>'

    bounce_pct = pct(bounce, total)
    classes = ["ma-cell", heat_class(bounce_pct)]
    if total < MIN_SAMPLE:
        classes.append("low-confidence")
    return (
        f'<td class="{" ".join(classes)}">'
        f'<span class="pct">{bounce_pct}%</span> <span class="sample">(n={total})</span>'
        "</td>"
    )


def render_html_detail_cell(values: list[int], ma_index: int) -> str:
    total, bounce, break_count, false_count = count_block(values, ma_index)
    if total == 0:
        return '<td class="no-data">—</td>'

    bounce_pct = pct(bounce, total)
    break_pct = pct(break_count, total)
    false_pct = pct(false_count, total)
    return (
        "<td>"
        f'<span class="detail-b">{bounce_pct}</span> / '
        f'<span class="detail-bk">{break_pct}</span> / '
        f'<span class="detail-f">{false_pct}</span> '
        f'<span class="sample">(n={total})</span>'
        "</td>"
    )


def render_html_best_cell(values: list[int]) -> str:
    best = best_parts(values)
    if best is None:
        return '<td class="best-cell no-best">—</td>'

    name, best_pct = best
    return (
        '<td class="best-cell">'
        f"<strong>{html.escape(name)}</strong> <span>{best_pct}%</span>"
        "</td>"
    )


def collect_setups(daily_snapshot: dict, weekly_snapshot: dict) -> list[dict]:
    setups: list[dict] = []
    for tf_label, snapshot in (("D", daily_snapshot), ("W", weekly_snapshot)):
        data = snapshot["data"]
        for ticker in universe_tickers():
            values = data[ticker]
            for ma_index, ma_name in enumerate(MA_NAMES):
                total, bounce, break_count, false_count = count_block(values, ma_index)
                if total < MIN_SAMPLE:
                    continue
                setups.append(
                    {
                        "ticker": ticker,
                        "ma": ma_name,
                        "tf": tf_label,
                        "total": total,
                        "bounce_pct": pct(bounce, total),
                        "break_pct": pct(break_count, total),
                        "false_pct": pct(false_count, total),
                    }
                )
    return setups


def render_html_leaderboard(rows: list[dict], primary: str) -> str:
    primary_label = "Bounce%" if primary == "bounce_pct" else "Break%"
    body_rows: list[str] = []
    for index, row in enumerate(rows, start=1):
        body_rows.append(
            "<tr>"
            f'<td class="rank">{index}</td>'
            f'<td class="ticker">{html.escape(row["ticker"])}</td>'
            f'<td>{html.escape(row["ma"])}</td>'
            f'<td class="tf-cell">{row["tf"]}</td>'
            f'<td class="hl">{row[primary]}%</td>'
            f'<td class="sample">n={row["total"]}</td>'
            "</tr>"
        )
    return (
        '<table class="leaderboard">'
        "<thead><tr>"
        "<th>#</th><th>Ticker</th><th>MA</th><th>TF</th>"
        f"<th>{primary_label}</th><th>Events</th>"
        "</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
    )


def render_html_executive_summary(daily_snapshot: dict, weekly_snapshot: dict) -> str:
    setups = collect_setups(daily_snapshot, weekly_snapshot)
    if not setups:
        return ""

    daily_sets = [s for s in setups if s["tf"] == "D"]
    weekly_sets = [s for s in setups if s["tf"] == "W"]

    avg_bounce_d = round(sum(s["bounce_pct"] for s in daily_sets) / max(len(daily_sets), 1))
    avg_bounce_w = round(sum(s["bounce_pct"] for s in weekly_sets) / max(len(weekly_sets), 1))
    total_events_d = sum(s["total"] for s in daily_sets)
    total_events_w = sum(s["total"] for s in weekly_sets)

    top_mr = sorted(setups, key=lambda s: (-s["bounce_pct"], -s["total"]))[:5]
    top_bo = sorted(setups, key=lambda s: (-s["break_pct"], -s["total"]))[:5]

    return f"""
<section class="exec-summary">
  <h2>Executive Summary</h2>
  <div class="kpi-row">
    <div class="kpi"><span class="kpi-value">{avg_bounce_d}%</span><span class="kpi-label">Avg Bounce% — Daily</span></div>
    <div class="kpi"><span class="kpi-value">{avg_bounce_w}%</span><span class="kpi-label">Avg Bounce% — Weekly</span></div>
    <div class="kpi"><span class="kpi-value">{total_events_d:,}</span><span class="kpi-label">Daily events analyzed</span></div>
    <div class="kpi"><span class="kpi-value">{total_events_w:,}</span><span class="kpi-label">Weekly events analyzed</span></div>
  </div>
  <div class="exec-grid">
    <div class="exec-col">
      <h3>Top 5 Mean-Reversion Setups</h3>
      <p class="exec-caption">Highest Bounce% across the desk universe (n ≥ {MIN_SAMPLE}).</p>
      {render_html_leaderboard(top_mr, "bounce_pct")}
    </div>
    <div class="exec-col">
      <h3>Top 5 Breakout / Trending Setups</h3>
      <p class="exec-caption">Highest Break% — strongest follow-through after the touch.</p>
      {render_html_leaderboard(top_bo, "break_pct")}
    </div>
  </div>
</section>
"""


def render_html_summary_table(snapshot: dict, category_tickers: list[str]) -> str:
    rows = [
        "<table class=\"summary-table\">",
        "<thead><tr>",
        "<th>Ticker</th>",
        *(f"<th>{html.escape(ma_name)}</th>" for ma_name in MA_NAMES),
        "<th>Best</th>",
        "</tr></thead>",
        "<tbody>",
    ]

    data = snapshot["data"]
    for ticker in category_tickers:
        values = data[ticker]
        rows.append("<tr>")
        rows.append(f'<td class="ticker">{html.escape(ticker)}</td>')
        rows.extend(render_html_bounce_cell(values, ma_index) for ma_index in range(len(MA_NAMES)))
        rows.append(render_html_best_cell(values))
        rows.append("</tr>")

    rows.extend(["</tbody>", "</table>"])
    return "\n".join(rows)


def render_html_detail_table(snapshot: dict, category_tickers: list[str]) -> str:
    rows = [
        "<table class=\"detail-table\">",
        "<thead><tr>",
        "<th>Ticker</th>",
        *(f"<th>{html.escape(ma_name)}</th>" for ma_name in MA_NAMES),
        "</tr></thead>",
        "<tbody>",
    ]

    data = snapshot["data"]
    for ticker in category_tickers:
        rows.append("<tr>")
        rows.append(f'<td class="ticker">{html.escape(ticker)}</td>')
        rows.extend(render_html_detail_cell(data[ticker], ma_index) for ma_index in range(len(MA_NAMES)))
        rows.append("</tr>")

    rows.extend(["</tbody>", "</table>"])
    return "\n".join(rows)


def render_html_sections(table_kind: str, daily_snapshot: dict, weekly_snapshot: dict) -> str:
    parts: list[str] = []
    table_renderer = render_html_summary_table if table_kind == "summary" else render_html_detail_table

    for category_name, tickers in CATEGORIES:
        parts.append(f"<h2>{html.escape(category_name)}</h2>")
        for timeframe, snapshot in (("Daily", daily_snapshot), ("Weekly", weekly_snapshot)):
            parts.append('<section class="matrix-section" style="page-break-inside: avoid">')
            parts.append(f"<h3>{html.escape(timeframe)}</h3>")
            parts.append(table_renderer(snapshot, tickers))
            parts.append("</section>")

    return "\n".join(parts)


def render_html(daily_snapshot: dict, weekly_snapshot: dict, latest_date: str) -> str:
    daily_date = daily_snapshot["d"]
    weekly_date = weekly_snapshot["d"]
    total_tickers = len(universe_tickers())
    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    ma_list = ", ".join(MA_NAMES)

    css = """
@page {
  size: A4;
  margin: 14mm 12mm 14mm 12mm;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: #ffffff;
  color: #1a1f2e;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  font-size: 10pt;
  line-height: 1.35;
  print-color-adjust: exact;
  -webkit-print-color-adjust: exact;
}

header {
  border-top: 3px solid #c89e3a;
  padding: 12px 0 14px 0;
  margin-bottom: 14px;
}

h1 {
  margin: 0 0 8px 0;
  color: #0d1f3c;
  font-size: 22pt;
  line-height: 1.05;
  font-weight: 750;
  letter-spacing: 0;
}

.subtitle-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5px 18px;
  margin: 8px 0 12px 0;
  color: #5a6378;
}

.meta-item strong {
  color: #1a1f2e;
  font-weight: 650;
}

.read-box {
  background: #f6f7fb;
  border-left: 3px solid #0d1f3c;
  padding: 10px 14px;
  color: #1a1f2e;
}

.read-box h2 {
  border: 0;
  margin: 0 0 5px 0;
  padding: 0;
}

.read-box ul {
  margin: 0;
  padding-left: 16px;
}

.read-box li {
  margin: 2px 0;
}

h2 {
  margin: 17px 0 7px 0;
  padding-bottom: 3px;
  border-bottom: 1px solid #0d1f3c;
  color: #0d1f3c;
  font-size: 13pt;
  line-height: 1.2;
  font-weight: 720;
  letter-spacing: 0;
}

h3 {
  margin: 9px 0 5px 0;
  color: #3d465a;
  font-size: 11pt;
  line-height: 1.2;
  font-weight: 680;
  letter-spacing: 0;
}

.matrix-section {
  margin-bottom: 10px;
  page-break-inside: avoid;
  break-inside: avoid;
}

table {
  width: 100%;
  border-collapse: collapse;
  border: 1px solid #d6dae3;
  margin: 0 0 7px 0;
  table-layout: fixed;
}

th,
td {
  border: 1px solid #e7eaf0;
  padding: 5px 7px;
  vertical-align: middle;
  font-size: 9pt;
  font-variant-numeric: tabular-nums;
}

th {
  background: #0d1f3c;
  color: #ffffff;
  font-weight: 650;
  text-align: center;
}

tr {
  page-break-inside: avoid;
  break-inside: avoid;
}

.ticker {
  width: 11%;
  color: #0d1f3c;
  font-weight: 760;
  text-align: left;
}

.summary-table th,
.summary-table td {
  text-align: center;
}

.summary-table .ticker,
.detail-table .ticker {
  text-align: left;
}

.ma-cell {
  font-weight: 640;
}

.sample {
  font-weight: 460;
  white-space: nowrap;
}

.low-confidence {
  opacity: 0.55;
}

.heat-0 {
  background: #fde2e2;
  color: #7a1f1f;
}

.heat-1 {
  background: #fdedd2;
  color: #6e4d18;
}

.heat-2 {
  background: #fff8d6;
  color: #5d5418;
}

.heat-3 {
  background: #e1f1d6;
  color: #345417;
}

.heat-4 {
  background: #bfe5b0;
  color: #1f4012;
}

.heat-5 {
  background: #94d27a;
  color: #143008;
}

.no-data {
  background: #f0f0f0;
  color: #9aa0a6;
  font-weight: 560;
}

.best-cell {
  background: #0d1f3c;
  color: #ffffff;
  font-weight: 520;
  text-align: center;
}

.best-cell strong {
  font-weight: 800;
}

.best-cell span {
  font-weight: 450;
  color: #dbe4f4;
}

.best-cell.no-best {
  color: #dbe4f4;
}

.detail-table tbody tr:nth-child(even) {
  background: #fafbfd;
}

.detail-table td {
  text-align: center;
  color: #2c3446;
}

.detail-b,
.detail-bk,
.detail-f {
  font-weight: 650;
}

.notes {
  margin-top: 16px;
  color: #343c50;
}

.notes ul {
  margin: 5px 0 0 0;
  padding-left: 16px;
}

.exec-summary {
  margin: 4px 0 18px 0;
  page-break-inside: avoid;
  break-inside: avoid;
}

.exec-summary h2 {
  margin-top: 0;
}

.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin: 8px 0 12px 0;
}

.kpi {
  background: linear-gradient(135deg, #0d1f3c 0%, #1c3461 100%);
  color: #ffffff;
  border-radius: 6px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.kpi-value {
  font-size: 18pt;
  font-weight: 760;
  line-height: 1.05;
  color: #f3c969;
  font-variant-numeric: tabular-nums;
}

.kpi-label {
  font-size: 8pt;
  font-weight: 520;
  letter-spacing: 0.3pt;
  text-transform: uppercase;
  color: #c9d4ec;
  margin-top: 3px;
}

.exec-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.exec-col h3 {
  margin: 0 0 4px 0;
  color: #0d1f3c;
}

.exec-caption {
  margin: 0 0 6px 0;
  font-size: 8.5pt;
  color: #5a6378;
}

.leaderboard {
  width: 100%;
  border-collapse: collapse;
  border: 1px solid #d6dae3;
}

.leaderboard th {
  background: #0d1f3c;
  color: #ffffff;
  padding: 5px 6px;
  font-size: 8.5pt;
  font-weight: 650;
}

.leaderboard td {
  padding: 5px 7px;
  font-size: 9pt;
  font-variant-numeric: tabular-nums;
  border: 1px solid #e7eaf0;
}

.leaderboard td.rank {
  width: 7%;
  text-align: center;
  color: #7a8396;
  font-weight: 700;
}

.leaderboard td.ticker {
  width: 22%;
  color: #0d1f3c;
  font-weight: 720;
}

.leaderboard td.tf-cell {
  width: 8%;
  text-align: center;
  font-weight: 620;
  color: #3d465a;
}

.leaderboard td.hl {
  width: 18%;
  text-align: center;
  background: #fff8d6;
  color: #5d3d0a;
  font-weight: 800;
}

.leaderboard td.sample {
  width: 15%;
  text-align: center;
  color: #5a6378;
  font-weight: 480;
}

.footer {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid #d6dae3;
  color: #7a8396;
  font-size: 8pt;
}
"""

    exec_summary_html = render_html_executive_summary(daily_snapshot, weekly_snapshot)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Occurrence Matrix Report - {html.escape(latest_date)}</title>
  <style>
{css}
  </style>
</head>
<body>
  <header>
    <h1>Occurrence Matrix Report</h1>
    <div class="subtitle-grid">
      <div class="meta-item"><strong>Report date:</strong> {html.escape(latest_date)}</div>
      <div class="meta-item"><strong>Snapshots:</strong> Daily {html.escape(daily_date)} &nbsp;·&nbsp; Weekly {html.escape(weekly_date)}</div>
      <div class="meta-item"><strong>Universe:</strong> {total_tickers} tickers across {len(CATEGORIES)} categories</div>
      <div class="meta-item"><strong>Parameters:</strong> Zone Tolerance 0.1% &nbsp;·&nbsp; Lookahead 2 candles &nbsp;·&nbsp; Min sample {MIN_SAMPLE}</div>
      <div class="meta-item"><strong>MAs evaluated:</strong> {html.escape(ma_list)}</div>
    </div>
    <div class="read-box">
      <h2>How to Read</h2>
      <ul>
        <li><strong>Bounce%</strong> = % of events where the close returned to the original side (mean reversion).</li>
        <li><strong>Break%</strong> = % of events where the close persisted on the opposite side for 2 candles.</li>
        <li><strong>False%</strong> = % of events with an intra-bar violation that reverted to the original side.</li>
        <li><strong>Best</strong> = MA with the highest Bounce% in the row, only with n ≥ {MIN_SAMPLE}. Low-sample cells are dimmed.</li>
      </ul>
    </div>
  </header>

  <main>
    {exec_summary_html}

    <h2>Summary - Bounce%</h2>
    {render_html_sections("summary", daily_snapshot, weekly_snapshot)}

    <section class="notes">
      <h2>Breakdown - Bounce / Break / False</h2>
      <p>Each cell shows <strong>B / Bk / F (n=T)</strong>. High Break% indicates a firm break-through; high False% indicates intra-bar noise.</p>
    </section>
    {render_html_sections("detail", daily_snapshot, weekly_snapshot)}

    <section class="notes">
      <h2>Notes</h2>
      <ul>
        <li><strong>VWAP unavailable on XSP and RUT</strong> - the CBOE:XSP / TVC:RUT feed does not provide VWAP on Daily/Weekly. Marked as “—”.</li>
        <li><strong>Insufficient sample</strong> (n &lt; {MIN_SAMPLE}) blocks the entry in the Best column, but the percentage is still shown with the (n=T) suffix.</li>
        <li>Raw snapshots: <code>state/occurrence_matrix_snapshots/</code></li>
      </ul>
    </section>
  </main>

  <footer class="footer">
    Regen: <code>python scripts/occurrence_matrix_report.py --format all</code><br>
    Generated at {html.escape(generated_at)}
  </footer>
</body>
</html>
"""


def render_summary_section(category_name: str, timeframe: str, snapshot: dict, tickers: list[str]) -> list[str]:
    lines = [f"## {category_name} — {timeframe}", ""]
    lines.extend(render_summary_table(snapshot, tickers))
    return lines


def render_detail_section(category_name: str, timeframe: str, snapshot: dict, tickers: list[str]) -> list[str]:
    lines = [f"### {category_name} — {timeframe}"]
    lines.extend(render_detail_table(snapshot, tickers))
    return lines


def output_path(args: argparse.Namespace, latest_date: str) -> Path:
    if args.out_path:
        return Path(args.out_path).expanduser().resolve()
    return DEFAULT_REPORT_DIR / f"occurrence_matrix_report_{latest_date}.md"


def output_paths(args: argparse.Namespace, latest_date: str) -> tuple[Path, Path, Path]:
    md_path = output_path(args, latest_date)
    base_path = md_path.with_suffix("")
    return md_path, base_path.with_suffix(".html"), base_path.with_suffix(".pdf")


def find_chrome(arg: Optional[str]) -> Path:
    candidates: list[Path] = []

    if arg:
        candidates.append(Path(arg).expanduser())

    env_path = os.environ.get("CHROME_PATH")
    if env_path:
        candidates.append(Path(env_path).expanduser())

    candidates.extend(
        [
            Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
            Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
            Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    searched = "\n".join(f"  - {candidate}" for candidate in candidates)
    raise FileNotFoundError(
        "Chrome/Edge executable not found. Use --chrome <path> or set CHROME_PATH.\n"
        f"Searched:\n{searched}"
    )


def convert_html_to_pdf(html_path: Path, pdf_path: Path, chrome: Path) -> None:
    import tempfile
    import time

    if pdf_path.exists():
        pdf_path.unlink()

    with tempfile.TemporaryDirectory(prefix="om_chrome_", ignore_cleanup_errors=True) as user_data_dir:
        command = [
            str(chrome),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-crash-reporter",
            "--disable-crashpad",
            "--disable-breakpad",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={user_data_dir}",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path.resolve()}",
            html_path.resolve().as_uri(),
        ]
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 90
        prev_size = -1
        try:
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    break
                if pdf_path.exists():
                    size = pdf_path.stat().st_size
                    if size > 0 and size == prev_size:
                        break
                    prev_size = size
                time.sleep(0.5)
        finally:
            if proc.poll() is None:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass

    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise RuntimeError(f"Chrome did not produce a PDF at {pdf_path}")


def latest_report_date(daily_snapshot: dict, weekly_snapshot: dict) -> str:
    daily_date = date.fromisoformat(daily_snapshot["d"])
    weekly_date = date.fromisoformat(weekly_snapshot["d"])
    return max(daily_date, weekly_date).isoformat()


def main() -> None:
    args = parse_args()

    daily_path = snapshot_path_for(args.daily_date, "D") if args.daily_date else discover_latest_snapshot("D")
    weekly_path = snapshot_path_for(args.weekly_date, "W") if args.weekly_date else discover_latest_snapshot("W")

    daily_snapshot = load_snapshot(daily_path, "D")
    weekly_snapshot = load_snapshot(weekly_path, "W")
    latest_date = latest_report_date(daily_snapshot, weekly_snapshot)

    md_path, html_path, pdf_path = output_paths(args, latest_date)
    requested_format = args.output_format
    write_md = requested_format in {"md", "all"}
    write_html = requested_format in {"html", "pdf", "all"}
    write_pdf = requested_format in {"pdf", "all"}

    if write_md:
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_report(daily_snapshot, weekly_snapshot, latest_date), encoding="utf-8")
        print(md_path.resolve())

    if write_html:
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(render_html(daily_snapshot, weekly_snapshot, latest_date), encoding="utf-8")
        if requested_format in {"html", "all"}:
            print(html_path.resolve())

    if write_pdf:
        try:
            chrome = find_chrome(args.chrome_path)
            convert_html_to_pdf(html_path, pdf_path, chrome)
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as exc:
            print(f"ERROR: PDF generation failed. HTML kept at: {html_path.resolve()}", file=sys.stderr)
            if isinstance(exc, subprocess.CalledProcessError):
                print(f"Command exited with code {exc.returncode}.", file=sys.stderr)
                if exc.stderr:
                    print(exc.stderr, file=sys.stderr)
            elif isinstance(exc, subprocess.TimeoutExpired):
                print("Chrome timed out after 60 seconds.", file=sys.stderr)
                if exc.stderr:
                    stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr
                    print(stderr, file=sys.stderr)
            else:
                print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc

        print(pdf_path.resolve())
        if requested_format == "pdf" and not args.keep_html:
            html_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
