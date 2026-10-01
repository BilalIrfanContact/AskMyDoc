from .ai_providers import VoyageEmbeddings, embedding_model


def get_embedding_model() -> VoyageEmbeddings:
    """The metered embedding model used for both documents and questions (see `ai_providers`)."""
    return embedding_model()
