import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from backend.services import usage_ledger
from backend.services.usage_dashboard import render_dashboard


class UsageTestCase(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._env = patch.dict(os.environ, {"AI_USAGE_DIR": self._dir.name, "AI_MONTHLY_BUDGET_USD": "5"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._dir.cleanup()


class UsageLedgerTestCase(UsageTestCase):
    def test_record_prices_the_call_and_adds_it_to_this_months_spend(self):
        cost = usage_ledger.record("groq", "openai/gpt-oss-120b", "answer", 1_000_000, 100_000)

        self.assertAlmostEqual(cost, 0.15 + 0.06)
        self.assertAlmostEqual(usage_ledger.month_spend(), 0.21)
        self.assertTrue((usage_ledger.usage_directory() / "dashboard.html").exists())

    def test_spend_from_earlier_months_does_not_count(self):
        # 18:59 UTC on Aug 31 is 23:59 in Pakistan, still August; 19:30 UTC is already September there.
        groq = {"provider": "groq", "model": "openai/gpt-oss-20b", "task": "answer", "input_tokens": 1, "output_tokens": 0}
        entries = [{**groq, "time": "2026-08-31T18:59:00+00:00", "cost_usd": 4.99},
                   {**groq, "time": "2026-08-31T19:30:00+00:00", "cost_usd": 0.5}]

        self.assertEqual(usage_ledger.month_spend(entries, now=datetime(2026, 9, 1, tzinfo=timezone.utc)), 0.5)

    def test_free_allowance_calls_bill_nothing_and_only_tokens_past_it_are_billed(self):
        def call(time, tokens):
            return {"time": time, "provider": "voyage", "model": "voyage-4-lite", "task": "embed-document",
                    "input_tokens": tokens, "output_tokens": 0, "cost_usd": tokens * 0.02 / 1_000_000}

        entries = [call("2026-10-01T10:00:00+00:00", 150_000_000), call("2026-10-02T10:00:00+00:00", 100_000_000)]
        first, second = usage_ledger.with_billing(entries)

        self.assertEqual(first["billed_usd"], 0)
        self.assertAlmostEqual(second["billed_usd"], 50_000_000 * 0.02 / 1_000_000)  # only the 50M past 200M
        self.assertAlmostEqual(usage_ledger.month_spend(entries, now=datetime(2026, 10, 3, tzinfo=timezone.utc)), 1.0)

    def test_free_embedding_calls_do_not_use_up_the_budget(self):
        usage_ledger.record("voyage", "voyage-4-lite", "embed-document", 199_000_000)

        self.assertEqual(usage_ledger.month_spend(), 0)
        usage_ledger.ensure_budget("groq", "openai/gpt-oss-20b")

    def test_paid_calls_stop_once_the_budget_is_spent(self):
        usage_ledger.record("groq", "openai/gpt-oss-120b", "answer", 40_000_000)

        with self.assertRaises(usage_ledger.BudgetExceeded):
            usage_ledger.ensure_budget("groq", "openai/gpt-oss-20b")

    def test_embeddings_still_covered_by_free_tokens_work_after_the_budget_is_spent(self):
        usage_ledger.record("groq", "openai/gpt-oss-120b", "answer", 40_000_000)
        usage_ledger.ensure_budget("voyage", "voyage-4-lite")

        usage_ledger.record("voyage", "voyage-4-lite", "embed-document", 200_000_000)
        with self.assertRaises(usage_ledger.BudgetExceeded):
            usage_ledger.ensure_budget("voyage", "voyage-4-lite")

    def test_a_model_without_a_price_cannot_be_called(self):
        with self.assertRaises(usage_ledger.UnpricedModel):
            usage_ledger.ensure_budget("groq", "some-unpriced-model")


class UsageDashboardTestCase(unittest.TestCase):
    def test_shows_this_months_spend_against_the_budget(self):
        now = datetime(2026, 10, 6, tzinfo=timezone.utc)
        entries = [
            {"time": "2026-10-05T10:00:00+00:00", "provider": "groq", "model": "openai/gpt-oss-20b",
             "task": "label", "input_tokens": 900, "output_tokens": 100, "cost_usd": 1.25},
            {"time": "2026-09-30T10:00:00+00:00", "provider": "groq", "model": "openai/gpt-oss-20b",
             "task": "label", "input_tokens": 900, "output_tokens": 100, "cost_usd": 3.0},
        ]

        page = render_dashboard(entries, 5.0, now)

        self.assertIn("$1.25", page)
        self.assertIn('<dt>Left this month</dt><dd class="num">$3.75</dd>', page)
        self.assertIn("Labelling chunks", page)

    def test_shows_free_embedding_calls_as_covered_not_billed(self):
        now = datetime(2026, 10, 6, tzinfo=timezone.utc)
        entries = [{"time": "2026-10-05T10:00:00+00:00", "provider": "voyage", "model": "voyage-4-lite",
                    "task": "embed-document", "input_tokens": 5_000_000, "output_tokens": 0, "cost_usd": 0.1}]

        page = render_dashboard(entries, 5.0, now)

        self.assertIn('<dt>Left this month</dt><dd class="num">$5.00</dd>', page)
        self.assertIn('<dt>Covered by free tokens</dt><dd class="num">$0.10</dd>', page)
        self.assertIn("195.0M<small>of 200.0M tokens left", page)


if __name__ == "__main__":
    unittest.main()
