from pathlib import Path
import unittest

from backend.main import app
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

    def test_openapi_declares_authz_forbidden_responses(self):
        openapi_schema = app.openapi()

        routes = [
            ("/chat", "post"),
            ("/conversations", "get"),
            ("/conversations", "post"),
            ("/conversations/{conversation_id}/messages", "get"),
            ("/documents/{document_id}", "delete"),
        ]

        for path, method in routes:
            with self.subTest(path=path, method=method):
                responses = openapi_schema["paths"][path][method]["responses"]
                self.assertIn("403", responses)


if __name__ == "__main__":
    unittest.main()
