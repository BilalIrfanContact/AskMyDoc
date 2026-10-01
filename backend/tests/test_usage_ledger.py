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
        entries = [{"time": "2026-08-31T23:59:00+00:00", "cost_usd": 4.99}]

        self.assertEqual(usage_ledger.month_spend(entries, now=datetime(2026, 9, 1, tzinfo=timezone.utc)), 0)

    def test_paid_calls_stop_once_the_budget_is_spent(self):
        usage_ledger.record("groq", "openai/gpt-oss-120b", "answer", 40_000_000)

        with self.assertRaises(usage_ledger.BudgetExceeded):
            usage_ledger.ensure_budget("groq", "openai/gpt-oss-20b")

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


if __name__ == "__main__":
    unittest.main()
