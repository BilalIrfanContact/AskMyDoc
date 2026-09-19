import json
import os
from dataclasses import dataclass
from typing import Callable

from langchain_openai import ChatOpenAI

from .rag_adapters import ChromaRetrievalAdapter, OpenAIChatAdapter
from .rag_pipeline import GenerationAdapter, RetrievalAdapter
from .vector_store import get_vector_store


class SuggestionGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class QuestionSuggestionDependencies:
    retrieval_factory: Callable[[str], RetrievalAdapter]
    generation: GenerationAdapter


def _default_dependencies() -> QuestionSuggestionDependencies:
    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-5.4-nano")
    return QuestionSuggestionDependencies(
        retrieval_factory=lambda document_id: ChromaRetrievalAdapter(
            get_vector_store(document_id=document_id),
        ),
        generation=OpenAIChatAdapter(ChatOpenAI(model=model, temperature=0)),
    )


def _response_text(response: object) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            item if isinstance(item, str) else item.get("text", "")
            for item in content
            if isinstance(item, str) or isinstance(item, dict)
        ).strip()
    return str(content).strip()


def _parse_questions(response_text: str) -> list[str]:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise SuggestionGenerationError("Question suggestions were not valid JSON.") from exc

    raw_questions = payload.get("questions") if isinstance(payload, dict) else None
    if not isinstance(raw_questions, list):
        raise SuggestionGenerationError("Question suggestions were missing the questions list.")

    questions: list[str] = []
    for value in raw_questions:
        if not isinstance(value, str):
            continue
        question = " ".join(value.split()).strip()
        if not question:
            continue
        if not question.endswith("?"):
            question = f"{question}?"
        if len(question) > 160:
            question = f"{question[:159].rstrip(' ?')}?"
        if question in questions:
            continue
        questions.append(question)
        if len(questions) == 3:
            break

    if not questions:
        raise SuggestionGenerationError("No usable question suggestions were generated.")
    return questions


def generate_question_suggestions(
    document_id: str,
    *,
    dependencies: QuestionSuggestionDependencies | None = None,
) -> list[str]:
    active_dependencies = dependencies or _default_dependencies()
    retriever = active_dependencies.retrieval_factory(document_id)
    total_chunks = retriever.count()
    context = retriever.retrieve(
        "head",
        "",
        min(6, max(1, total_chunks or 4)),
    ).text.strip()
    if not context:
        return []

    prompt = (
        "Create three concise questions a reader would genuinely want to ask about this document.\n"
        "Every question must be specific to and answerable from the supplied excerpts.\n"
        "Avoid generic prompts such as 'Summarize this document'.\n"
        "Return only valid JSON in this exact shape: "
        '{"questions":["Question one?","Question two?","Question three?"]}.\n\n'
        f"Document excerpts:\n{context}\n\nJSON Response:"
    )

    try:
        response = active_dependencies.generation.invoke(prompt)
    except Exception as exc:
        raise SuggestionGenerationError("Failed to generate questions for this document.") from exc

    return _parse_questions(_response_text(response))
