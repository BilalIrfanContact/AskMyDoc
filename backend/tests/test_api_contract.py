from pathlib import Path
import unittest

from backend.scripts.generate_frontend_api_contract import render_frontend_contract


class ApiContractTestCase(unittest.TestCase):
    def test_generated_frontend_contract_is_in_sync(self):
        contract_path = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "api-contract.ts"
        expected = render_frontend_contract()
        actual = contract_path.read_text(encoding="utf-8")

        self.assertEqual(
            actual,
            expected,
            "frontend/lib/api-contract.ts is out of date. Regenerate it with "
            "`python -m backend.scripts.generate_frontend_api_contract`.",
        )


if __name__ == "__main__":
    unittest.main()
