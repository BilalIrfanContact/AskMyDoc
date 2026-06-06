import os

from dotenv import load_dotenv


RUNTIME_DEFAULTS = {
    "ANONYMIZED_TELEMETRY": "false",
    "CHROMA_TELEMETRY": "false",
    "CHROMA_ENABLE_TELEMETRY": "false",
    "POSTHOG_DISABLED": "1",
}


def apply_runtime_defaults() -> None:
    for name, value in RUNTIME_DEFAULTS.items():
        os.environ.setdefault(name, value)


def initialize_backend_environment() -> None:
    apply_runtime_defaults()
    load_dotenv()
