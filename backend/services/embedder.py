from langchain_openai import OpenAIEmbeddings


def get_embedding_model() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model="text-embedding-3-small")
