"""Small completed exchanges used to resolve references, never as document evidence."""
from dataclasses import dataclass
from typing import Sequence

MAX_HISTORY_EXCHANGES = 3
MAX_HISTORY_MESSAGE_CHARS = 1_000


@dataclass(frozen=True)
class ConversationExchange:
    question: str
    answer: str


def bounded_history(exchanges: Sequence[ConversationExchange]) -> tuple[ConversationExchange, ...]:
    return tuple(
        ConversationExchange(
            question=exchange.question[:MAX_HISTORY_MESSAGE_CHARS],
            answer=exchange.answer[:MAX_HISTORY_MESSAGE_CHARS],
        )
        for exchange in exchanges[-MAX_HISTORY_EXCHANGES:]
    )
