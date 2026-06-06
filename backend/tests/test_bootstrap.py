import os
import sys
import unittest
from importlib import import_module
from unittest.mock import patch

from backend.bootstrap import apply_runtime_defaults, initialize_backend_environment
from backend.services import vector_store


class BootstrapTestCase(unittest.TestCase):
    def test_apply_runtime_defaults_sets_expected_values(self):
        with patch.dict(os.environ, {}, clear=True):
            apply_runtime_defaults()

            self.assertEqual(os.environ["ANONYMIZED_TELEMETRY"], "false")
            self.assertEqual(os.environ["CHROMA_TELEMETRY"], "false")
            self.assertEqual(os.environ["CHROMA_ENABLE_TELEMETRY"], "false")
            self.assertEqual(os.environ["POSTHOG_DISABLED"], "1")

    def test_apply_runtime_defaults_does_not_override_existing_values(self):
        with patch.dict(
            os.environ,
            {
                "ANONYMIZED_TELEMETRY": "true",
                "CHROMA_TELEMETRY": "true",
                "CHROMA_ENABLE_TELEMETRY": "true",
                "POSTHOG_DISABLED": "0",
            },
            clear=True,
        ):
            apply_runtime_defaults()

            self.assertEqual(os.environ["ANONYMIZED_TELEMETRY"], "true")
            self.assertEqual(os.environ["CHROMA_TELEMETRY"], "true")
            self.assertEqual(os.environ["CHROMA_ENABLE_TELEMETRY"], "true")
            self.assertEqual(os.environ["POSTHOG_DISABLED"], "0")

    def test_initialize_backend_environment_loads_dotenv_and_applies_defaults(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("backend.bootstrap.load_dotenv") as load_dotenv_mock,
        ):
            initialize_backend_environment()

            self.assertEqual(os.environ["ANONYMIZED_TELEMETRY"], "false")
            self.assertEqual(os.environ["CHROMA_TELEMETRY"], "false")
            self.assertEqual(os.environ["CHROMA_ENABLE_TELEMETRY"], "false")
            self.assertEqual(os.environ["POSTHOG_DISABLED"], "1")

            load_dotenv_mock.assert_called_once_with()

    def test_importing_main_initializes_backend_environment(self):
        sys.modules.pop("backend.main", None)

        with patch("backend.bootstrap.initialize_backend_environment") as initialize_mock:
            import_module("backend.main")

        initialize_mock.assert_called_once_with()
        sys.modules.pop("backend.main", None)

    def test_disable_chroma_telemetry_applies_runtime_defaults(self):
        with patch("backend.services.vector_store.apply_runtime_defaults") as defaults_mock:
            vector_store._disable_chroma_telemetry()

        defaults_mock.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
