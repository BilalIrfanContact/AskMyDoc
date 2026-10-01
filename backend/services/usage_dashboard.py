"""Render the local AI spending dashboard from the usage ledger.

A developer-only HTML file at `backend/usage/dashboard.html` (gitignored), rebuilt after every recorded
call and reloading itself every 30 seconds. It isn't served by the app. To rebuild it by hand:

    .venv/bin/python -m backend.services.usage_dashboard
"""

from __future__ import annotations

import calendar
import html
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


Row = tuple[str, int, int, float]

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


def _job(entry: dict[str, Any]) -> str:
    return JOB_NAMES.get(entry["task"], entry["task"])


def _grouped(entries: list[dict[str, Any]], key: Callable[[dict[str, Any]], str]) -> list[Row]:
    groups: dict[str, list[float]] = defaultdict(lambda: [0, 0, 0.0])
    for entry in entries:
        group = groups[key(entry)]
        group[0] += 1
        group[1] += entry["input_tokens"] + entry["output_tokens"]
        group[2] += entry["cost_usd"]
    return sorted(((name, int(c), int(t), cost) for name, (c, t, cost) in groups.items()), key=lambda row: -row[3])


def _card(content: str, area: str, index: int) -> str:
    """A panel in the nested "tray and plate" style: an outer shell holding the content core."""
    return f'<section class="shell reveal {area}" style="--i:{index}"><div class="core">{content}</div></section>'


def _breakdown(title: str, rows: Iterable[Row], total: float) -> str:
    items = "".join(
        f"""<li>
  <div class="line"><span class="name">{html.escape(name)}</span><span class="num">{_money(cost)}</span></div>
  <div class="share"><i style="--s:{(cost / total) if total else 0:.4f}"></i></div>
  <div class="meta num">{calls:,} calls <span>{tokens:,} tokens</span></div>
</li>"""
        for name, calls, tokens, cost in rows
    )
    return f'<h2>{title}</h2><ul class="breakdown">{items}</ul>'


def _daily_chart(entries: list[dict[str, Any]], now: datetime) -> str:
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    per_day = [0.0] * days_in_month
    for entry in entries:
        per_day[int(entry["time"][8:10]) - 1] += entry["cost_usd"]
    peak = max(per_day) or 1.0
    bars = "".join(
        f'<div class="day {"today" if day == now.day else "future" if day > now.day else ""}" '
        f'title="{now.strftime("%b")} {day}: {_money(cost)}" '
        f'style="--h:{max(cost / peak, 0.02) if day <= now.day else 0.02:.4f};--d:{day}">'
        f'<i></i>{f"<span>{day}</span>" if day == 1 or day % 5 == 0 else ""}</div>'
        for day, cost in enumerate(per_day, start=1)
    )
    busiest = max(range(days_in_month), key=lambda index: per_day[index])
    note = f"Busiest day: {now.strftime('%b')} {busiest + 1}, {_money(per_day[busiest])}" if any(per_day) else "No spend yet"
    return f'<div class="chart-head"><h2>Spend by day</h2><span class="dim">{note}</span></div><div class="chart">{bars}</div>'


def render_dashboard(entries: list[dict[str, Any]], budget: float, now: datetime | None = None) -> str:
    """This month's spend against the budget, broken down by provider, day, model and job."""
    now = now or datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    current = [entry for entry in entries if entry["time"].startswith(month)]
    spent = sum(entry["cost_usd"] for entry in current)
    share = min(spent / budget, 1.0) if budget else 1.0
    state = "ok" if share < 0.4 else "warn" if share < 0.8 else "stop"
    remaining = max(budget - spent, 0.0)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    elapsed_days = (now.day - 1) + (now.hour * 60 + now.minute) / 1440
    projected = spent / elapsed_days * days_in_month if elapsed_days >= 1 else None

    summary = f"""
<div class="summary {state}">
  <div class="hero-number">{_money(spent)}<small>of ${budget:.2f}</small></div>
  <div class="meter" role="img" aria-label="{share * 100:.0f}% of the monthly budget used"><i style="--s:{share:.4f}"></i></div>
  <dl class="stats">
    <div><dt>Left this month</dt><dd class="num">{_money(remaining)}</dd></div>
    <div><dt>At this pace, by month end</dt><dd class="num">{_money(projected) if projected is not None else "Too early"}</dd></div>
    <div><dt>Calls this month</dt><dd class="num">{len(current):,}</dd></div>
  </dl>
</div>"""

    cards = [_card(summary, "a-summary", 0)]
    if current:
        recent = "".join(
            f"<tr><td class='num'>{html.escape(entry['time'][5:16].replace('T', ' ').replace('-', '/'))}</td>"
            f"<td>{html.escape(_job(entry))}</td>"
            f"<td class='num r'>{entry['input_tokens'] + entry['output_tokens']:,}</td>"
            f"<td class='num r'>{_money(entry['cost_usd'])}</td></tr>"
            for entry in reversed(current[-12:])
        )
        cards += [
            _card(_breakdown("By provider", _grouped(current, lambda e: e["provider"].capitalize()), spent), "a-provider", 1),
            _card(_daily_chart(current, now), "a-daily", 2),
            _card(_breakdown("By model", _grouped(current, lambda e: e["model"]), spent), "a-model", 3),
            _card(_breakdown("By job", _grouped(current, _job), spent), "a-jobs", 4),
            _card(
                "<h2>Latest calls</h2><div class='scroll'><table><thead><tr><th>When (UTC)</th><th>Job</th>"
                f"<th class='r'>Tokens</th><th class='r'>Cost</th></tr></thead><tbody>{recent}</tbody></table></div>",
                "a-calls",
                5,
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
<title>{_money(spent)} of ${budget:.2f} | AskMyDoc AI spend</title>
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
  --accent:#0e8a5c; --warn:#b7791f; --stop:#c2410c; --glow:rgba(14,138,92,.10); --ease:cubic-bezier(.16,1,.3,1);
  --sans:"Geist","Satoshi",ui-sans-serif,system-ui,sans-serif; --mono:"Geist Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#070808; --shell:rgba(255,255,255,.028); --shell-line:rgba(255,255,255,.07); --core:#0d0f11;
          --highlight:rgba(255,255,255,.06); --ink:#ececee; --dim:#8a8d96; --line:rgba(255,255,255,.07);
          --accent:#3ecf8e; --warn:#e8b04b; --stop:#f0714a; --glow:rgba(62,207,142,.09); }}
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
.a-daily {{ grid-column:span 8; }} .a-model {{ grid-column:span 4; }}
.a-jobs {{ grid-column:span 5; }} .a-calls {{ grid-column:span 7; }}
.shell {{ padding:6px; border-radius:28px; background:var(--shell); border:1px solid var(--shell-line); }}
.core {{ height:100%; border-radius:22px; background:var(--core); padding:28px 30px;
  box-shadow:inset 0 1px 0 var(--highlight), 0 24px 60px -40px rgba(10,40,30,.35); }}
h2 {{ margin:0 0 20px; font-size:14px; font-weight:500; color:var(--dim); letter-spacing:-.005em; }}
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
.share i {{ background:var(--accent); opacity:.7; }}
.meta {{ font-size:12px; color:var(--dim); }} .meta span {{ margin-left:10px; }}
.chart-head {{ display:flex; justify-content:space-between; align-items:baseline; gap:16px; }}
.chart-head span {{ font-size:13px; }}
.chart {{ display:grid; grid-auto-flow:column; grid-auto-columns:minmax(0,1fr); gap:5px; height:190px; align-items:end; padding-bottom:22px; }}
.day {{ position:relative; height:100%; display:flex; align-items:flex-end; }}
.day i {{ display:block; width:100%; height:100%; border-radius:5px; background:var(--accent); opacity:.4;
  transform-origin:bottom; transform:scaleY(var(--h)); transition:opacity .5s var(--ease); }}
.day:hover i {{ opacity:.85; }} .day.today i {{ opacity:1; }} .day.future i {{ background:var(--line); opacity:1; }}
.day span {{ position:absolute; bottom:-22px; left:50%; translate:-50% 0; font:11px var(--mono); color:var(--dim); }}
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
  html:not(.still) .day i {{ animation:grow 1s var(--ease) both; animation-delay:calc(var(--d) * 18ms + 300ms); }}
}}
@keyframes rise {{ to {{ opacity:1; transform:none; filter:none; }} }}
@keyframes fill {{ from {{ transform:scaleX(0); }} }}
@keyframes grow {{ from {{ transform:scaleY(0); }} }}
@media (max-width:1023px) {{
  .a-summary, .a-provider, .a-daily, .a-model, .a-jobs, .a-calls {{ grid-column:span 12; }}
}}
@media (max-width:767px) {{
  main {{ padding:40px 16px 72px; }}
  .top {{ flex-direction:column; align-items:flex-start; }} .updated {{ text-align:left; }}
  .bento {{ gap:14px; }} .core {{ padding:22px; }}
  .stats {{ grid-template-columns:1fr; gap:14px; }}
  .chart {{ gap:3px; height:150px; }}
}}
</style></head><body><main>
<header class="top reveal" style="--i:0">
  <div><span class="eyebrow">AI spend</span><h1>{now.strftime("%B %Y")}</h1></div>
  <div class="updated">Updated {now.strftime("%d %b, %H:%M")} UTC<br>Estimated from reported tokens and list prices</div>
</header>
<div class="bento">
{"".join(cards)}
</div>
</main></body></html>
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
