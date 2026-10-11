"""One-time import of the old local AI spend ledger (`backend/usage/ledger.jsonl`) into Supabase's `ai_usage`.

Carrying the history over keeps this month's spend and the Voyage free-allowance count, since the deployed app
uses the same provider accounts. Refuses to run if `ai_usage` already has rows, so nothing is counted twice.

    .venv/bin/python -m backend.scripts.import_usage_ledger          # report only
    .venv/bin/python -m backend.scripts.import_usage_ledger --apply  # import
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from postgrest.types import ReturnMethod

from backend.services.persistence.common import get_postgrest_client
from backend.services.usage_ledger import local_now, month_spend, usage_totals


LEDGER = Path(__file__).resolve().parents[1] / "usage/ledger.jsonl"
BATCH_SIZE = 500


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import the local AI spend ledger into Supabase.")
    parser.add_argument("--apply", action="store_true", help="Write to Supabase; without it, only report.")
    parser.add_argument("--ledger", type=Path, default=LEDGER, help="Ledger file to import.")
    args = parser.parse_args(argv)

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    client = get_postgrest_client()
    if client.from_("ai_usage").select("id").limit(1).execute().data:
        print("ai_usage already has rows; nothing imported.", file=sys.stderr)
        return 1

    rows = [
        {
            "created_at": entry["time"],
            "provider": entry["provider"],
            "model": entry["model"],
            "task": entry["task"],
            "input_tokens": entry["input_tokens"],
            "output_tokens": entry["output_tokens"],
            "cost_usd": entry["cost_usd"],
        }
        for entry in map(json.loads, filter(str.strip, args.ledger.read_text(encoding="utf-8").splitlines()))
    ]
    if not args.apply:
        print(f"Would import {len(rows)} calls from {args.ledger}.", file=sys.stderr)
        return 0
    for start in range(0, len(rows), BATCH_SIZE):
        client.from_("ai_usage").insert(rows[start : start + BATCH_SIZE], returning=ReturnMethod.minimal).execute()
    print(
        f"Imported {len(rows)} calls. Billed spend for {local_now():%B %Y} is now ${month_spend(usage_totals()):.4f}.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
