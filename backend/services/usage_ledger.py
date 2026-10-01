"""Record what every AI call costs, and stop paid calls once the month's budget is spent.

Every chat and embedding call goes through `ai_providers`, which calls `ensure_budget()` before the
request and `record()` after it with the token counts the provider reported. Each call becomes one JSON
line in `backend/usage/ledger.jsonl` (gitignored; `AI_USAGE_DIR` moves it), priced from `PRICES`, and the local dashboard
(`usage_dashboard.py`) is rebuilt from the ledger.

Costs are our own estimate (reported tokens × list price), not the provider's invoice. Voyage's free
token allowance is ignored, so embedding costs are counted as if paid; that errs on the safe side.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_USAGE_DIRECTORY = Path(__file__).resolve().parents[1] / "usage"
DEFAULT_MONTHLY_BUDGET_USD = 5.0

# USD per 1M tokens: (input, output). List prices from the providers' pricing pages, checked 2026-09-27
# (see docs/research/cheaper-ai-provider.md). A model missing here can't be called, so no spend goes
# unrecorded; add its price before using it.
PRICES: dict[tuple[str, str], tuple[float, float]] = {
    ("groq", "openai/gpt-oss-20b"): (0.075, 0.30),
    ("groq", "openai/gpt-oss-120b"): (0.15, 0.60),
    ("voyage", "voyage-4-lite"): (0.02, 0.0),
    ("voyage", "voyage-finance-2"): (0.12, 0.0),
}

_lock = threading.Lock()


class BudgetExceeded(RuntimeError):
    """Raised instead of making a paid AI call once this month's recorded spend reaches the budget."""


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


def month_spend(entries: list[dict[str, Any]] | None = None, now: datetime | None = None) -> float:
    """Recorded spend for the current calendar month (UTC)."""
    month = (now or datetime.now(timezone.utc)).strftime("%Y-%m")
    entries = read_entries() if entries is None else entries
    return sum(entry["cost_usd"] for entry in entries if entry["time"].startswith(month))


def ensure_budget(provider: str, model: str) -> None:
    """Check the model is priced and this month's budget isn't used up, before a paid call."""
    price_of(provider, model)
    spent = month_spend()
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
