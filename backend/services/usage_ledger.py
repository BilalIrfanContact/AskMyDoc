"""Record what every AI call costs, and stop paid calls once the month's budget is spent.

Every chat and embedding call goes through `ai_providers`, which calls `ensure_budget()` before the
request and `record()` after it with the token counts the provider reported. Each call becomes one row in
Supabase's `ai_usage` table (see `supabase/migrations/202610110002_ai_usage.sql`), priced from `PRICES`, so the
budget survives restarts. `ensure_budget` works from per-model totals (`usage_totals`) rather than reading every
row; the spending dashboard (`python -m backend.services.usage_dashboard`) reads every row with `read_entries`.

Costs are our own estimate (reported tokens × list price), not the provider's invoice. Each call keeps its
list-price cost; `with_billing` works out how much of it a free token allowance covered, and only the billed
remainder counts against the monthly budget.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from postgrest.types import ReturnMethod

from .persistence.common import get_postgrest_client


DEFAULT_USAGE_DIRECTORY = Path(__file__).resolve().parents[1] / "usage"
DEFAULT_MONTHLY_BUDGET_USD = 5.0

# Supabase's API returns at most 1,000 rows per request.
PAGE_SIZE = 1000

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

class BudgetExceeded(RuntimeError):
    """Raised instead of making a paid AI call once this month's billed spend reaches the budget."""


class UnpricedModel(ValueError):
    """Raised for a model with no entry in `PRICES`."""


def usage_directory() -> Path:
    """Where the dashboard is written; `AI_USAGE_DIR` overrides it."""
    return Path(os.getenv("AI_USAGE_DIR") or DEFAULT_USAGE_DIRECTORY)


def monthly_budget() -> float:
    return float(os.getenv("AI_MONTHLY_BUDGET_USD", DEFAULT_MONTHLY_BUDGET_USD))


def price_of(provider: str, model: str) -> tuple[float, float]:
    try:
        return PRICES[(provider, model)]
    except KeyError:
        raise UnpricedModel(f"No price recorded for {provider} model {model!r}; add it to usage_ledger.PRICES.") from None


def read_entries() -> list[dict[str, Any]]:
    """Every recorded call, oldest first, with its UTC timestamp as `time`."""
    rows: list[dict[str, Any]] = []
    while True:
        page = (
            get_postgrest_client()
            .from_("ai_usage")
            .select("created_at, provider, model, task, input_tokens, output_tokens, cost_usd")
            .order("id")
            .range(len(rows), len(rows) + PAGE_SIZE - 1)
            .execute()
            .data
            or []
        )
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
    return [{"time": row.pop("created_at"), **row} for row in rows]


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


def usage_totals(now: datetime | None = None) -> list[dict[str, Any]]:
    """Per model: tokens used before `now`'s month, and tokens and list-price cost within it (Pakistan time)."""
    start = (now or local_now()).astimezone(LOCAL_TIMEZONE).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return (
        get_postgrest_client()
        .rpc("ai_usage_totals", {"p_month_start": start.isoformat(), "p_month_end": end.isoformat()})
        .execute()
        .data
        or []
    )


def month_spend(totals: list[dict[str, Any]] | None = None) -> float:
    """Billed spend (after free allowances) for the current calendar month, in Pakistan time.

    The same result `with_billing` gives call by call: a month's tokens are free while the allowance left at
    the month's start lasts, and the rest bill at their share of the month's list-price cost.
    """
    spent = 0.0
    for row in usage_totals() if totals is None else totals:
        tokens = row["tokens_in_month"]
        if not tokens:
            continue
        free_left = max(FREE_TOKENS.get((row["provider"], row["model"]), 0) - row["tokens_before"], 0)
        spent += row["cost_in_month"] * (tokens - min(tokens, free_left)) / tokens
    return spent


def free_tokens_left(provider: str, model: str, totals: list[dict[str, Any]]) -> int:
    """Tokens of the model's one-time free allowance not yet used, across the ledger's whole history."""
    used = sum(
        row["tokens_before"] + row["tokens_in_month"] for row in totals if (row["provider"], row["model"]) == (provider, model)
    )
    return max(FREE_TOKENS.get((provider, model), 0) - used, 0)


def ensure_budget(provider: str, model: str, estimated_tokens: int | None = None) -> None:
    """Before a call, check the model is priced and the call is free or this month's budget isn't spent.

    A call whose `estimated_tokens` fit in the model's remaining free allowance is always allowed, so free
    embeddings keep working after paid chat spends the budget. Without an estimate, only the budget counts.
    """
    price_of(provider, model)
    totals = usage_totals()
    if estimated_tokens is not None and estimated_tokens <= free_tokens_left(provider, model, totals):
        return
    spent = month_spend(totals)
    budget = monthly_budget()
    if spent >= budget:
        raise BudgetExceeded(
            f"This month's AI budget is used up (${spent:.2f} of ${budget:.2f}). "
            "AskMyDoc can't upload or answer until next month or until the budget is raised."
        )


def record(provider: str, model: str, task: str, input_tokens: int, output_tokens: int = 0) -> float:
    """Add one call to the ledger and return its cost."""
    input_price, output_price = price_of(provider, model)
    cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
    entry = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": provider,
        "model": model,
        "task": task,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 8),
    }
    get_postgrest_client().from_("ai_usage").insert(entry, returning=ReturnMethod.minimal).execute()
    return cost
