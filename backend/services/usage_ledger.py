"""Record what every AI call costs, and stop paid calls once the month's budget is spent.

Every chat and embedding call goes through `ai_providers`, which calls `ensure_budget()` before the
request and `record()` after it with the token counts the provider reported. Each call becomes one JSON
line in `backend/usage/ledger.jsonl` (gitignored; `AI_USAGE_DIR` moves it), priced from `PRICES`, and the local dashboard
(`usage_dashboard.py`) is rebuilt from the ledger.

Costs are our own estimate (reported tokens × list price), not the provider's invoice. Each call keeps its
list-price cost; `with_billing` works out how much of it a free token allowance covered, and only the billed
remainder counts against the monthly budget.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_USAGE_DIRECTORY = Path(__file__).resolve().parents[1] / "usage"
DEFAULT_MONTHLY_BUDGET_USD = 5.0

# The ledger stores UTC timestamps; months, days and displayed times use Pakistan time.
LOCAL_TIMEZONE = ZoneInfo("Asia/Karachi")

# USD per 1M tokens: (input, output). List prices from the providers' pricing pages, checked 2026-09-27
# (see docs/research/cheaper-ai-provider.md). A model missing here can't be called, so no spend goes
# unrecorded; add its price before using it.
PRICES: dict[tuple[str, str], tuple[float, float]] = {
    ("groq", "openai/gpt-oss-20b"): (0.075, 0.30),
    ("groq", "openai/gpt-oss-120b"): (0.15, 0.60),
    ("voyage", "voyage-4-lite"): (0.02, 0.0),
    ("voyage", "voyage-finance-2"): (0.12, 0.0),
}

# Free tokens granted once per account (not monthly), as shown on the Voyage dashboard on 2026-09-29.
# Calls inside the allowance cost nothing; only tokens past it are billed and count against the budget.
# Assumes every call goes through AskMyDoc, so usage from the Voyage playground isn't seen here.
FREE_TOKENS: dict[tuple[str, str], int] = {
    ("voyage", "voyage-4-lite"): 200_000_000,
    ("voyage", "voyage-finance-2"): 50_000_000,
}

_lock = threading.Lock()


class BudgetExceeded(RuntimeError):
    """Raised instead of making a paid AI call once this month's billed spend reaches the budget."""


class UnpricedModel(ValueError):
    """Raised for a model with no entry in `PRICES`."""


def usage_directory() -> Path:
    """Where the ledger and dashboard live; `AI_USAGE_DIR` overrides it (tests use a temporary one)."""
    return Path(os.getenv("AI_USAGE_DIR") or DEFAULT_USAGE_DIRECTORY)


def ledger_path() -> Path:
    return usage_directory() / "ledger.jsonl"


def monthly_budget() -> float:
    return float(os.getenv("AI_MONTHLY_BUDGET_USD", DEFAULT_MONTHLY_BUDGET_USD))


def price_of(provider: str, model: str) -> tuple[float, float]:
    try:
        return PRICES[(provider, model)]
    except KeyError:
        raise UnpricedModel(f"No price recorded for {provider} model {model!r}; add it to usage_ledger.PRICES.") from None


def read_entries(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or ledger_path()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def local_now() -> datetime:
    return datetime.now(LOCAL_TIMEZONE)


def local_time(entry: dict[str, Any]) -> datetime:
    """An entry's timestamp in Pakistan time."""
    return datetime.fromisoformat(entry["time"]).astimezone(LOCAL_TIMEZONE)


def in_month(entries: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """The entries from `now`'s calendar month, in Pakistan time."""
    month = now.astimezone(LOCAL_TIMEZONE).strftime("%Y-%m")
    return [entry for entry in entries if local_time(entry).strftime("%Y-%m") == month]


def with_billing(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copies of `entries` with `billed_usd`: the part of `cost_usd` (list price) not covered by free tokens.

    Free allowances are used up in call order across the ledger's whole history.
    """
    used: dict[tuple[str, str], int] = {}
    billed = []
    for entry in sorted(entries, key=lambda e: datetime.fromisoformat(e["time"])):
        key = (entry["provider"], entry["model"])
        tokens = entry["input_tokens"] + entry["output_tokens"]
        free_left = max(FREE_TOKENS.get(key, 0) - used.get(key, 0), 0)
        used[key] = used.get(key, 0) + tokens
        billable = tokens - min(tokens, free_left)
        billed.append({**entry, "billed_usd": entry["cost_usd"] * billable / tokens if tokens else 0.0})
    return billed


def free_allowances(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each free allowance that has been drawn on: tokens granted, tokens used so far, and their list-price value."""
    rows = []
    for (provider, model), granted in FREE_TOKENS.items():
        calls = [e for e in entries if (e["provider"], e["model"]) == (provider, model)]
        if calls:
            used = sum(e["input_tokens"] + e["output_tokens"] for e in calls)
            rows.append({"provider": provider, "model": model, "granted": granted, "used": used,
                         "price_per_million": PRICES[(provider, model)][0]})
    return rows


def month_spend(entries: list[dict[str, Any]] | None = None, now: datetime | None = None) -> float:
    """Billed spend (after free allowances) for the current calendar month, in Pakistan time."""
    entries = read_entries() if entries is None else entries
    return sum(entry["billed_usd"] for entry in in_month(with_billing(entries), now or local_now()))


def free_tokens_left(provider: str, model: str, entries: list[dict[str, Any]]) -> int:
    """Tokens of the model's one-time free allowance not yet used, across the ledger's whole history."""
    used = sum(e["input_tokens"] + e["output_tokens"] for e in entries if (e["provider"], e["model"]) == (provider, model))
    return max(FREE_TOKENS.get((provider, model), 0) - used, 0)


def ensure_budget(provider: str, model: str, estimated_tokens: int | None = None) -> None:
    """Before a call, check the model is priced and the call is free or this month's budget isn't spent.

    A call whose `estimated_tokens` fit in the model's remaining free allowance is always allowed, so free
    embeddings keep working after paid chat spends the budget. Without an estimate, only the budget counts.
    """
    price_of(provider, model)
    entries = read_entries()
    if estimated_tokens is not None and estimated_tokens <= free_tokens_left(provider, model, entries):
        return
    spent = month_spend(entries)
    budget = monthly_budget()
    if spent >= budget:
        raise BudgetExceeded(
            f"This month's AI budget is used up (${spent:.2f} of ${budget:.2f}). "
            "AskMyDoc can't upload or answer until next month or until the budget is raised."
        )


def record(provider: str, model: str, task: str, input_tokens: int, output_tokens: int = 0) -> float:
    """Append one call to the ledger, rebuild the dashboard, and return the call's cost."""
    input_price, output_price = price_of(provider, model)
    cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
    entry = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": provider,
        "model": model,
        "task": task,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 8),
    }
    with _lock:
        usage_directory().mkdir(parents=True, exist_ok=True)
        with ledger_path().open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps(entry) + "\n")
        try:
            from .usage_dashboard import write_dashboard

            write_dashboard(read_entries(), monthly_budget())
        except Exception:
            pass  # The ledger is the record; a dashboard failure must never fail an AI call.
    return cost
