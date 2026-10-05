"""The only place AskMyDoc creates AI clients: Groq for chat, Voyage for embeddings.

Every call goes through a metered wrapper that checks the monthly budget first and records the tokens
the provider reported afterwards (see `usage_ledger`). Code that needs a model asks for one by job:

    chat_adapter("answer").invoke(prompt)
    embedding_model().embed_documents(texts)

Models are chosen per job with environment variables (defaults in brackets):
- `AI_CHAT_MODEL` [openai/gpt-oss-20b]: chunk labels, evidence picking, suggested questions
- `AI_ANSWER_MODEL` [openai/gpt-oss-20b]: question routing, summaries and the cited answer
- `AI_GRADER_MODEL` [openai/gpt-oss-120b]: the eval grader
- `AI_EMBEDDING_MODEL` [voyage-4-lite]: document and question embeddings
Keys come from `GROQ_API_KEY` and `VOYAGE_API_KEY`.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from langchain_core.embeddings import Embeddings
from langchain_openai import ChatOpenAI

from .usage_ledger import ensure_budget, record


GROQ_BASE_URL = "https://api.groq.com/openai/v1"
VOYAGE_EMBEDDINGS_URL = "https://api.voyageai.com/v1/embeddings"

DEFAULT_CHAT_MODEL = "openai/gpt-oss-20b"
DEFAULT_GRADER_MODEL = "openai/gpt-oss-120b"
DEFAULT_EMBEDDING_MODEL = "voyage-4-lite"
_RETRIES = 6

# gpt-oss models think before answering, and that hidden thinking is billed as output. Labels don't need it:
# at the default effort a label averaged ~490 output tokens and some spent the whole cap thinking and came
# back empty; at "low" they take ~100-150 tokens.
REASONING_EFFORT = {"label": "low"}


def chat_model_for(task: str) -> str:
    if task == "answer":
        return os.getenv("AI_ANSWER_MODEL", DEFAULT_CHAT_MODEL)
    if task == "grade":
        return os.getenv("AI_GRADER_MODEL", DEFAULT_GRADER_MODEL)
    return os.getenv("AI_CHAT_MODEL", DEFAULT_CHAT_MODEL)


def embedding_model_name() -> str:
    return os.getenv("AI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)


class MeteredChat:
    """A Groq chat model behind the app's `invoke(prompt)` seam, metered per call.

    The client is created on the first call, so building an adapter that ends up unused costs nothing.
    """

    provider = "groq"

    def __init__(self, task: str, model: str | None = None):
        self.task = task
        self.model = model or chat_model_for(task)
        self._llm = None

    def invoke(self, prompt: str) -> Any:
        ensure_budget(self.provider, self.model)
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=self.model,
                temperature=0,
                base_url=GROQ_BASE_URL,
                api_key=os.getenv("GROQ_API_KEY"),
                max_retries=_RETRIES,
                model_kwargs={"reasoning_effort": REASONING_EFFORT[self.task]} if self.task in REASONING_EFFORT else {},
            )
        response = self._llm.invoke(prompt)
        input_tokens, output_tokens = _reported_tokens(response, prompt)
        record(self.provider, self.model, self.task, input_tokens, output_tokens)
        return response


def chat_adapter(task: str, model: str | None = None) -> MeteredChat:
    """A metered chat model for one job: answer, route, rerank, label, suggest, plan or grade."""
    return MeteredChat(task, model)


def _reported_tokens(response: Any, prompt: str) -> tuple[int, int]:
    """Tokens the provider reported, or a rough over-estimate (4 characters per token) if it didn't."""
    usage = getattr(response, "usage_metadata", None) or {}
    if usage.get("input_tokens") is not None:
        return int(usage["input_tokens"]), int(usage.get("output_tokens") or 0)
    token_usage = (getattr(response, "response_metadata", None) or {}).get("token_usage") or {}
    if token_usage.get("prompt_tokens") is not None:
        return int(token_usage["prompt_tokens"]), int(token_usage.get("completion_tokens") or 0)
    content = getattr(response, "content", "")
    return len(prompt) // 4 + 1, len(content if isinstance(content, str) else str(content)) // 4 + 1


class VoyageEmbeddings(Embeddings):
    """Voyage embeddings, metered. Documents and questions use Voyage's matching input types."""

    provider = "voyage"

    def __init__(self, model: str | None = None):
        self.model = model or embedding_model_name()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(list(texts), "document") if texts else []

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "query")[0]

    def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        # One token per 2 characters overestimates English text, so a call is treated as free only if
        # it surely fits in what's left of the free allowance.
        ensure_budget(self.provider, self.model, estimated_tokens=sum(len(text) for text in texts) // 2 + len(texts))
        payload = {"input": texts, "model": self.model, "input_type": input_type}
        headers = {"Authorization": f"Bearer {os.getenv('VOYAGE_API_KEY', '')}"}
        for attempt in range(_RETRIES):
            response = httpx.post(VOYAGE_EMBEDDINGS_URL, json=payload, headers=headers, timeout=120)
            if response.status_code not in (429, 500, 502, 503, 504) or attempt == _RETRIES - 1:
                break
            time.sleep(min(30, 2**attempt))
        response.raise_for_status()
        body = response.json()
        record(self.provider, self.model, f"embed-{input_type}", int(body["usage"]["total_tokens"]))
        return [item["embedding"] for item in sorted(body["data"], key=lambda item: item["index"])]


def embedding_model() -> VoyageEmbeddings:
    return VoyageEmbeddings()
