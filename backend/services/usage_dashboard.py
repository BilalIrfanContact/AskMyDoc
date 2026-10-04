"""Render the local AI spending dashboard from the usage ledger.

A developer-only HTML file at `backend/usage/dashboard.html` (gitignored), rebuilt after every recorded
call and reloading itself every 30 seconds. It isn't served by the app. To rebuild it by hand:

    .venv/bin/python -m backend.services.usage_dashboard
"""

from __future__ import annotations

import calendar
import html
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from .usage_ledger import LOCAL_TIMEZONE, free_allowances, in_month, local_now, local_time, with_billing


# (name, calls, tokens, billed cost, list-price cost)
Row = tuple[str, int, int, float, float]

# SVG user units for the daily chart; the svg stretches to fill its box, so only the proportions matter.
CHART_WIDTH, CHART_HEIGHT = 1000, 200

# Plain names for the `task` recorded with each call.
JOB_NAMES = {
    "answer": "Answering questions",
    "rerank": "Picking evidence",
    "label": "Labelling chunks",
    "suggest": "Suggested questions",
    "grade": "Grading eval answers",
    "plan": "Planning searches",
    "embed-document": "Fingerprinting documents",
    "embed-query": "Fingerprinting questions",
}


def _money(value: float) -> str:
    if 0 < value < 0.0001:
        return "<$0.0001"
    return f"${value:.4f}" if 0 < value < 0.01 else f"${value:.2f}"


def _tokens(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    return f"{value / 1_000:.1f}K" if value >= 1_000 else f"{value:,.0f}"


def _split(billed: float, listed: float) -> str:
    """CSS variable for a two-tone bar: the billed share of a bar whose full length is the list-price cost."""
    return f"--b:{(billed / listed) if listed else 1:.4f}"


def _billed_cell(entry: dict[str, Any]) -> str:
    if entry["billed_usd"] > 0 or not entry["cost_usd"]:
        return _money(entry["billed_usd"])
    return f'<span class="pill" title="{_money(entry["cost_usd"])} at list price">free</span>'


def _job(entry: dict[str, Any]) -> str:
    return JOB_NAMES.get(entry["task"], entry["task"])


def _grouped(entries: list[dict[str, Any]], key: Callable[[dict[str, Any]], str]) -> list[Row]:
    groups: dict[str, list[float]] = defaultdict(lambda: [0, 0, 0.0, 0.0])
    for entry in entries:
        group = groups[key(entry)]
        group[0] += 1
        group[1] += entry["input_tokens"] + entry["output_tokens"]
        group[2] += entry["billed_usd"]
        group[3] += entry["cost_usd"]
    rows = ((name, int(c), int(t), billed, listed) for name, (c, t, billed, listed) in groups.items())
    return sorted(rows, key=lambda row: (-row[3], -row[4]))


def _card(content: str, area: str, index: int) -> str:
    """A panel in the nested "tray and plate" style: an outer shell holding the content core."""
    return f'<section class="shell reveal {area}" style="--i:{index}"><div class="core">{content}</div></section>'


def _breakdown(title: str, rows: Iterable[Row]) -> str:
    """Billed cost per group; each bar's length is its list-price share, solid where billed, faded where free."""
    rows = list(rows)
    total = sum(row[4] for row in rows)
    items = "".join(
        f"""<li>
  <div class="line"><span class="name">{html.escape(name)}</span><span class="num">{_money(billed)}</span></div>
  <div class="share"><i style="--s:{(listed / total) if total else 0:.4f};{_split(billed, listed)}"></i></div>
  <div class="meta num">{calls:,} calls <span>{tokens:,} tokens</span>{
      f'<span class="free">{_money(listed - billed)} covered free</span>' if listed - billed > 0 else ''}</div>
</li>"""
        for name, calls, tokens, billed, listed in rows
    )
    return f'<h2>{title}</h2><ul class="breakdown">{items}</ul>'


def _nice_ticks(peak: float) -> list[float]:
    """Round y-axis values (0, 0.2, 0.4, ...) from zero to at or just above the peak."""
    if peak <= 0:
        return [0.0, 0.01]
    raw = peak / 4
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    return [step * i for i in range(math.ceil(peak / step - 1e-9) + 1)]


def _curve(points: list[tuple[float, float]]) -> str:
    """SVG path through the points as a monotone cubic: smooth, but never dipping below zero or overshooting a peak."""
    if len(points) < 2:
        return ""
    slopes = [(y1 - y0) / (x1 - x0) for (x0, y0), (x1, y1) in zip(points, points[1:])]
    # Harmonic mean of neighbouring slopes, flat at turning points; this is what keeps the curve monotone.
    tangents = [slopes[0], *(2 * a * b / (a + b) if a * b > 0 else 0.0 for a, b in zip(slopes, slopes[1:])), slopes[-1]]
    path = f"M{points[0][0]:.1f},{points[0][1]:.1f}"
    for (x0, y0), (x1, y1), m0, m1 in zip(points, points[1:], tangents, tangents[1:]):
        third = (x1 - x0) / 3
        path += f" C{x0 + third:.1f},{y0 + m0 * third:.1f} {x1 - third:.1f},{y1 - m1 * third:.1f} {x1:.1f},{y1:.1f}"
    return path


def _daily_chart(entries: list[dict[str, Any]], now: datetime) -> str:
    """Billed and free-covered spend per day as two smooth lines, with a crosshair tooltip for each day so far."""
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    billed = [0.0] * days_in_month
    listed = [0.0] * days_in_month
    for entry in entries:
        billed[local_time(entry).day - 1] += entry["billed_usd"]
        listed[local_time(entry).day - 1] += entry["cost_usd"]
    free = [max(l - b, 0.0) for b, l in zip(billed, listed)]
    ticks = _nice_ticks(max(billed + free))
    x = lambda day: (day - 1) / (days_in_month - 1)
    y = lambda value: 1 - value / ticks[-1]

    grid = "".join(f'<line class="grid" x1="0" x2="{CHART_WIDTH}" y1="{y(t) * CHART_HEIGHT:.1f}" '
                   f'y2="{y(t) * CHART_HEIGHT:.1f}"/>' for t in ticks)
    marks, dots = "", ""
    # Free first, so the billed line draws on top where they cross.
    for name, values in (("free", free), ("billed", billed)):
        points = [(x(day) * CHART_WIDTH, y(value) * CHART_HEIGHT) for day, value in enumerate(values[:now.day], start=1)]
        line = _curve(points)
        if line:
            marks += (f'<path class="area {name}" d="{line} L{points[-1][0]:.1f},{CHART_HEIGHT} '
                      f'L{points[0][0]:.1f},{CHART_HEIGHT} Z" fill="url(#fade-{name})"/><path class="stroke {name}" d="{line}"/>')
        dots += f'<i class="dot {name}" style="--x:{x(now.day):.4f};--y:{y(values[now.day - 1]):.4f}"></i>'
    gradients = "".join(
        f'<linearGradient id="fade-{name}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" class="{name}" stop-opacity=".22"/>'
        f'<stop offset="1" class="{name}" stop-opacity="0"/></linearGradient>' for name in ("free", "billed"))
    readouts = [[f"{now.strftime('%b')} {day}", _money(b), _money(f), round(y(b), 4), round(y(f), 4)]
                for day, (b, f) in enumerate(zip(billed[:now.day], free[:now.day]), start=1)]

    y_labels = "".join(f'<span style="--y:{y(t):.4f}">{_money(t)}</span>' for t in ticks)
    x_labels = "".join(f'<span style="--x:{x(day):.4f}">{day}</span>'
                       for day in range(1, days_in_month + 1) if day == 1 or day % 5 == 0)
    busiest = max(range(days_in_month), key=lambda index: billed[index])
    note = (f"Busiest day: {now.strftime('%b')} {busiest + 1}, {_money(billed[busiest])} billed" if any(billed)
            else f"Nothing billed yet, {_money(sum(listed))} covered free" if any(listed) else "No calls yet")
    legend = '<span class="legend"><i class="k-billed"></i>Billed <i class="k-free"></i>Covered free</span>'
    return f"""<div class="chart-head"><h2>Spend by day</h2><span class="dim">{note}</span></div>
<div class="graph">
  <div class="y-axis num">{y_labels}</div>
  <div class="plot" tabindex="0" aria-label="Spend by day. Hover, or use the arrow keys, to read each day."
       data-days="{html.escape(json.dumps(readouts))}" data-span="{days_in_month - 1}">
    <svg viewBox="0 0 {CHART_WIDTH} {CHART_HEIGHT}" preserveAspectRatio="none" aria-hidden="true">
      <defs>{gradients}</defs>{grid}{marks}
    </svg>
    {dots}<div class="cross"><i class="dot free"></i><i class="dot billed"></i></div><div class="tip"></div>
    <div class="x-axis num">{x_labels}</div>
  </div>
</div>{legend}"""


def _allowance_card(allowances: list[dict[str, Any]], month_tokens: dict[str, int], elapsed_days: float) -> str:
    """Free token allowances: what's left, what it would have cost, and how long it lasts at this month's pace."""
    items = []
    for row in allowances:
        left = max(row["granted"] - row["used"], 0)
        share = left / row["granted"]
        saved = min(row["used"], row["granted"]) * row["price_per_million"] / 1_000_000
        # A week of data before projecting, so one test run doesn't read as the normal pace.
        per_day = month_tokens.get(row["model"], 0) / elapsed_days if elapsed_days >= 7 else 0
        if not left:
            pace = f"Used up: now billed at ${row['price_per_million']:.2f} per 1M tokens"
        elif not per_day:
            pace = "Too early to project how long it lasts"
        else:
            days = left / per_day
            pace = (f"Lasts about {days / 365:.0f} years at this month's pace" if days > 730
                    else f"Lasts about {days / 30:.0f} months at this month's pace" if days > 60
                    else f"Runs out in about {days:.0f} days at this month's pace")
        state = "ok" if share > 0.5 else "warn" if share > 0.2 else "stop"
        items.append(f"""<div class="allowance {state}">
  <div class="line"><span class="name">{html.escape(row["provider"].capitalize())} · {html.escape(row["model"])}</span>
    <span class="num dim">{share * 100:.1f}% left</span></div>
  <div class="big num">{_tokens(left)}<small>of {_tokens(row["granted"])} tokens left</small></div>
  <div class="meter" role="img" aria-label="{share * 100:.0f}% of the free allowance left"><i style="--s:{share:.4f}"></i></div>
  <div class="meta num">{_tokens(row["used"])} used <span>worth {_money(saved)} at list price</span></div>
  <div class="meta">{pace}</div>
</div>""")
    return "<h2>Free allowance</h2>" + "".join(items)


def render_dashboard(entries: list[dict[str, Any]], budget: float, now: datetime | None = None) -> str:
    """This month's billed spend against the budget, with free-allowance coverage, by provider, day, model and job."""
    now = (now or local_now()).astimezone(LOCAL_TIMEZONE)
    entries = with_billing(entries)
    current = in_month(entries, now)
    spent = sum(entry["billed_usd"] for entry in current)
    covered = sum(entry["cost_usd"] for entry in current) - spent
    share = min(spent / budget, 1.0) if budget else 1.0
    state = "ok" if share < 0.4 else "warn" if share < 0.8 else "stop"
    remaining = max(budget - spent, 0.0)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    elapsed_days = (now.day - 1) + (now.hour * 60 + now.minute) / 1440
    projected = spent / elapsed_days * days_in_month if elapsed_days >= 1 else None

    summary = f"""
<div class="summary {state}">
  <span class="label">Billed this month</span>
  <div class="hero-number">{_money(spent) if spent else "$0.00"}<small>of ${budget:.2f}</small></div>
  <div class="meter" role="img" aria-label="{share * 100:.0f}% of the monthly budget used"><i style="--s:{share:.4f}"></i></div>
  <dl class="stats">
    <div><dt>Left this month</dt><dd class="num">{_money(remaining)}</dd></div>
    <div><dt>At this pace, by month end</dt><dd class="num">{_money(projected) if projected is not None else "Too early"}</dd></div>
    <div><dt>Covered by free tokens</dt><dd class="num">{_money(covered) if covered > 0 else "$0.00"}</dd></div>
  </dl>
</div>"""

    cards = [_card(summary, "a-summary", 0)]
    if current:
        month_tokens: dict[str, int] = defaultdict(int)
        for entry in current:
            month_tokens[entry["model"]] += entry["input_tokens"] + entry["output_tokens"]
        allowances = free_allowances(entries)
        recent = "".join(
            f"<tr><td class='num'>{local_time(entry).strftime('%m/%d %H:%M')}</td>"
            f"<td>{html.escape(_job(entry))}</td>"
            f"<td class='num r'>{entry['input_tokens'] + entry['output_tokens']:,}</td>"
            f"<td class='num r'>{_billed_cell(entry)}</td></tr>"
            for entry in reversed(current[-12:])
        )
        cards += [
            _card(_breakdown("By provider", _grouped(current, lambda e: e["provider"].capitalize())), "a-provider", 1),
            _card(_daily_chart(current, now), "a-daily", 2),
        ]
        if allowances:
            cards.append(_card(_allowance_card(allowances, month_tokens, elapsed_days), "a-free", 3))
        cards += [
            _card(_breakdown("By model", _grouped(current, lambda e: e["model"])), "a-model", 4),
            _card(_breakdown("By job", _grouped(current, _job)), "a-jobs", 5),
            _card(
                "<h2>Latest calls</h2><div class='scroll'><table><thead><tr><th>When (PKT)</th><th>Job</th>"
                f"<th class='r'>Tokens</th><th class='r'>Billed</th></tr></thead><tbody>{recent}</tbody></table></div>",
                "a-calls",
                6,
            ),
        ]
    else:
        cards.append(_card(
            "<h2>No AI calls this month yet</h2><p class='dim'>Every Groq or Voyage call AskMyDoc makes, from the app "
            "or from an eval script, shows up here within a few seconds.</p>",
            "a-provider a-empty",
            1,
        ))

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>{_money(spent) if spent else "$0.00"} billed of ${budget:.2f} | AskMyDoc AI spend</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script>
  // Entry animations play once per browser session, not on every 30-second reload.
  if (sessionStorage.getItem("spend-seen")) document.documentElement.classList.add("still");
  sessionStorage.setItem("spend-seen", "1");
</script>
<style>
:root {{
  --bg:#f3f3f1; --shell:rgba(20,20,24,.035); --shell-line:rgba(20,20,24,.07); --core:#ffffff;
  --highlight:rgba(255,255,255,.9); --ink:#17171a; --dim:#6c6c74; --line:rgba(20,20,24,.08);
  --accent:#0e8a5c; --free:rgba(14,138,92,.22); --free-line:#5fb894; --warn:#b7791f; --stop:#c2410c; --glow:rgba(14,138,92,.10); --ease:cubic-bezier(.16,1,.3,1);
  --sans:"Geist","Satoshi",ui-sans-serif,system-ui,sans-serif; --mono:"Geist Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#070808; --shell:rgba(255,255,255,.028); --shell-line:rgba(255,255,255,.07); --core:#0d0f11;
          --highlight:rgba(255,255,255,.06); --ink:#ececee; --dim:#8a8d96; --line:rgba(255,255,255,.07);
          --accent:#3ecf8e; --free:rgba(62,207,142,.2); --free-line:#1f8a5f; --warn:#e8b04b; --stop:#f0714a; --glow:rgba(62,207,142,.09); }}
}}
* {{ box-sizing:border-box; }}
html {{ background:var(--bg); }}
body {{ margin:0; min-height:100dvh; color:var(--ink); font:15px/1.5 var(--sans); -webkit-font-smoothing:antialiased; }}
body::before {{ content:""; position:fixed; inset:0; pointer-events:none;
  background:radial-gradient(60rem 36rem at 12% -8%, var(--glow), transparent 60%),
             radial-gradient(40rem 30rem at 100% 110%, var(--glow), transparent 65%); }}
main {{ position:relative; max-width:1240px; margin:0 auto; padding:72px 40px 120px; }}
.num {{ font-family:var(--mono); font-variant-numeric:tabular-nums; letter-spacing:-.01em; }}
.dim {{ color:var(--dim); }}
.top {{ display:flex; justify-content:space-between; align-items:flex-end; gap:24px; margin-bottom:40px; }}
.eyebrow {{ display:inline-block; border:1px solid var(--shell-line); background:var(--shell); border-radius:999px;
  padding:4px 12px; font-size:10.5px; font-weight:500; letter-spacing:.18em; text-transform:uppercase; color:var(--dim); }}
h1 {{ margin:14px 0 0; font-size:clamp(34px,4.4vw,52px); font-weight:600; letter-spacing:-.035em; line-height:1.05; }}
.updated {{ font-size:13px; color:var(--dim); text-align:right; }}
.bento {{ display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:18px; }}
.a-summary {{ grid-column:span 8; }} .a-provider {{ grid-column:span 4; }}
.a-daily {{ grid-column:span 8; }} .a-free {{ grid-column:span 4; }}
.a-model {{ grid-column:span 4; }} .a-jobs {{ grid-column:span 8; }} .a-calls {{ grid-column:span 12; }}
.shell {{ padding:6px; border-radius:28px; background:var(--shell); border:1px solid var(--shell-line); }}
.core {{ height:100%; border-radius:22px; background:var(--core); padding:28px 30px;
  box-shadow:inset 0 1px 0 var(--highlight), 0 24px 60px -40px rgba(10,40,30,.35); }}
h2 {{ margin:0 0 20px; font-size:14px; font-weight:500; color:var(--dim); letter-spacing:-.005em; }}
.label {{ display:block; font-size:13px; color:var(--dim); margin-bottom:10px; }}
.hero-number {{ font-size:clamp(56px,7vw,96px); font-weight:500; line-height:1; letter-spacing:-.045em; font-variant-numeric:tabular-nums; }}
.hero-number small {{ font:500 20px var(--sans); letter-spacing:0; color:var(--dim); margin-left:12px; }}
.meter {{ height:8px; border-radius:8px; background:var(--line); margin:28px 0 30px; overflow:hidden; }}
.meter i, .share i {{ display:block; height:100%; border-radius:inherit; transform-origin:left; transform:scaleX(var(--s)); }}
.ok .meter i {{ background:var(--accent); }} .warn .meter i {{ background:var(--warn); }} .stop .meter i {{ background:var(--stop); }}
.stats {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:20px; margin:0; }}
.stats dt {{ font-size:13px; color:var(--dim); }}
.stats dd {{ margin:4px 0 0; font-size:22px; font-weight:500; }}
.breakdown {{ list-style:none; margin:0; padding:0; display:grid; gap:18px; }}
.line {{ display:flex; justify-content:space-between; gap:16px; }}
.name {{ overflow-wrap:anywhere; }}
.share {{ height:3px; margin:8px 0 6px; }}
.share i {{ background:linear-gradient(to right, var(--accent) 0 calc(var(--b) * 100%), var(--free) 0); }}
.meta .free {{ display:block; margin-left:0; color:var(--accent); }}
.chart-head h2 {{ white-space:nowrap; }}
.allowance + .allowance {{ margin-top:26px; padding-top:22px; border-top:1px solid var(--line); }}
.allowance .big {{ font-size:34px; font-weight:500; letter-spacing:-.03em; margin:14px 0 0; line-height:1.1; }}
.allowance .big small {{ font:500 14px var(--sans); letter-spacing:0; color:var(--dim); margin-left:8px; }}
.allowance .meter {{ margin:18px 0 14px; height:6px; }}
.allowance .meta + .meta {{ margin-top:4px; }}
.pill {{ display:inline-block; padding:1px 9px; border-radius:999px; font-size:11.5px; color:var(--accent);
  background:var(--free); cursor:help; }}
.legend {{ display:flex; gap:8px; align-items:center; font-size:12px; color:var(--dim); margin-top:4px; }}
.legend i {{ width:14px; height:2px; border-radius:2px; display:inline-block; }}
.legend i + i, .legend .k-free {{ margin-left:10px; }}
.k-billed {{ background:var(--accent); }} .k-free {{ background:var(--free-line); }}
.meta {{ font-size:12px; color:var(--dim); }} .meta span {{ margin-left:10px; }}
.chart-head {{ display:flex; justify-content:space-between; align-items:baseline; gap:16px; }}
.chart-head span {{ font-size:13px; }}
.graph {{ display:grid; grid-template-columns:auto minmax(0,1fr); gap:12px; padding:8px 0 30px; }}
.y-axis, .plot {{ position:relative; height:190px; }}
.y-axis {{ min-width:4ch; }}
.y-axis span, .x-axis span {{ position:absolute; font-size:11px; color:var(--dim); white-space:nowrap; }}
.y-axis span {{ right:0; top:calc(var(--y) * 100%); translate:0 -50%; }}
.x-axis span {{ top:calc(100% + 10px); left:calc(var(--x) * 100%); translate:-50% 0; }}
.plot {{ outline:none; touch-action:pan-y; }}
.plot:focus-visible {{ outline:2px solid var(--accent); outline-offset:6px; border-radius:4px; }}
.plot svg {{ position:absolute; inset:0; width:100%; height:100%; overflow:visible; }}
.grid {{ stroke:var(--line); stroke-width:1; vector-effect:non-scaling-stroke; }}
.stroke {{ fill:none; stroke-width:2; stroke-linejoin:round; stroke-linecap:round; vector-effect:non-scaling-stroke; }}
.stroke.billed {{ stroke:var(--accent); }} .stroke.free {{ stroke:var(--free-line); }}
stop.billed {{ stop-color:var(--accent); }} stop.free {{ stop-color:var(--free-line); }}
.dot {{ position:absolute; left:calc(var(--x) * 100%); top:calc(var(--y) * 100%); width:8px; height:8px; border-radius:50%;
  translate:-50% -50%; box-shadow:0 0 0 2px var(--core); }}
.dot.billed {{ background:var(--accent); }} .dot.free {{ background:var(--free-line); }}
.cross {{ position:absolute; inset:0 auto 0 calc(var(--x) * 100%); width:1px; background:var(--line); display:none; }}
.cross .dot {{ left:0; }}
.tip {{ position:absolute; top:0; left:calc(var(--x) * 100%); translate:14px 0; display:none; min-width:150px; padding:10px 12px;
  border-radius:12px; background:var(--core); border:1px solid var(--shell-line); font-size:12px; pointer-events:none;
  box-shadow:0 12px 32px -16px rgba(0,0,0,.45); }}
.tip.flip {{ translate:calc(-100% - 14px) 0; }}
.tip b {{ display:block; font-weight:500; color:var(--dim); margin-bottom:6px; }}
.tip div {{ display:flex; align-items:center; gap:8px; }} .tip div + div {{ margin-top:3px; }}
.tip i {{ width:10px; height:2px; border-radius:2px; }} .tip strong {{ font-weight:500; }} .tip span {{ color:var(--dim); }}
.plot.active .cross, .plot.active .tip {{ display:block; }}
.scroll {{ overflow-x:auto; margin:0 -8px; }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
th {{ text-align:left; font-weight:500; font-size:12.5px; color:var(--dim); padding:0 8px 10px; }}
td {{ padding:9px 8px; white-space:nowrap; border-top:1px solid var(--line); transition:background-color .5s var(--ease); }}
tbody tr:hover td {{ background:var(--shell); }}
.r {{ text-align:right; }}
.a-empty p {{ margin:0; max-width:46ch; }}
@media (prefers-reduced-motion: no-preference) {{
  html:not(.still) .reveal {{ opacity:0; transform:translateY(18px); filter:blur(8px);
    animation:rise .9s var(--ease) forwards; animation-delay:calc(var(--i) * 80ms + 60ms); }}
  html:not(.still) .meter i {{ animation:fill 1.4s var(--ease) .35s both; }}
  html:not(.still) .share i {{ animation:fill 1.1s var(--ease) .5s both; }}
  html:not(.still) .plot svg {{ animation:draw 1.3s var(--ease) .3s both; }}
  html:not(.still) .plot > .dot {{ animation:pop .5s var(--ease) 1.3s both; }}
}}
@keyframes rise {{ to {{ opacity:1; transform:none; filter:none; }} }}
@keyframes fill {{ from {{ transform:scaleX(0); }} }}
@keyframes draw {{ from {{ clip-path:inset(0 100% 0 0); }} }}
@keyframes pop {{ from {{ opacity:0; }} }}
@media (max-width:1023px) {{
  .a-summary, .a-provider, .a-daily, .a-free, .a-model, .a-jobs, .a-calls {{ grid-column:span 12; }}
}}
@media (max-width:767px) {{
  main {{ padding:40px 16px 72px; }}
  .top {{ flex-direction:column; align-items:flex-start; }} .updated {{ text-align:left; }}
  .bento {{ gap:14px; }} .core {{ padding:22px; }}
  .stats {{ grid-template-columns:1fr; gap:14px; }}
  .y-axis, .plot {{ height:150px; }}
}}
</style></head><body><main>
<header class="top reveal" style="--i:0">
  <div><h1>{now.strftime("%B %Y")}</h1></div>
  <div class="updated">Updated {now.strftime("%d %b, %H:%M")} PKT<br>Billed after free allowances · estimated from reported tokens and list prices</div>
</header>
<div class="bento">
{"".join(cards)}
</div>
</main>
<script>
  // Daily chart crosshair: hover, or focus and use the arrow keys, to read both lines for one day.
  for (const plot of document.querySelectorAll(".plot")) {{
    const days = JSON.parse(plot.dataset.days), span = +plot.dataset.span;
    const cross = plot.querySelector(".cross"), tip = plot.querySelector(".tip");
    let current = days.length - 1;
    const show = index => {{
      current = Math.max(0, Math.min(index, days.length - 1));
      const [label, billed, free, yBilled, yFree] = days[current], x = current / span;
      plot.style.setProperty("--x", x);
      cross.querySelector(".billed").style.setProperty("--y", yBilled);
      cross.querySelector(".free").style.setProperty("--y", yFree);
      const row = (key, value, name) => {{
        const div = document.createElement("div"), swatch = document.createElement("i");
        swatch.className = key;
        div.append(swatch, Object.assign(document.createElement("strong"), {{textContent: value}}),
                   Object.assign(document.createElement("span"), {{textContent: name}}));
        return div;
      }};
      tip.replaceChildren(Object.assign(document.createElement("b"), {{textContent: label}}),
                          row("k-billed", billed, "billed"), row("k-free", free, "covered free"));
      tip.classList.toggle("flip", x > 0.6);
      plot.classList.add("active");
    }};
    const hide = () => plot.classList.remove("active");
    plot.addEventListener("pointermove", event => {{
      const box = plot.getBoundingClientRect(), index = Math.round((event.clientX - box.left) / box.width * span);
      index < days.length ? show(index) : hide();
    }});
    plot.addEventListener("pointerleave", hide);
    plot.addEventListener("focus", () => show(current));
    plot.addEventListener("blur", hide);
    plot.addEventListener("keydown", event => {{
      const step = {{ArrowLeft: -1, ArrowRight: 1}}[event.key];
      if (step) {{ event.preventDefault(); show(current + step); }}
    }});
  }}
</script>
</body></html>
"""


def write_dashboard(entries: list[dict[str, Any]], budget: float) -> Path:
    from .usage_ledger import usage_directory

    usage_directory().mkdir(parents=True, exist_ok=True)
    path = usage_directory() / "dashboard.html"
    path.write_text(render_dashboard(entries, budget), encoding="utf-8")
    return path


if __name__ == "__main__":
    from .usage_ledger import monthly_budget, read_entries

    print(write_dashboard(read_entries(), monthly_budget()))
