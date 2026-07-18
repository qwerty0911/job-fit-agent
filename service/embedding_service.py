from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import (
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_MODEL,
)


embeddings_model = OpenAIEmbeddings(
    model=EMBEDDING_MODEL,
    api_key=EMBEDDING_API_KEY,
    base_url=EMBEDDING_BASE_URL,
)

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def split_text(text: str) -> list[str]:
    return [
        chunk.strip()
        for chunk in text_splitter.split_text(text)
        if chunk.strip()
    ]


async def create_embeddings(chunks: list[str]) -> list[list[float]]:
    if not chunks:
        return []

    return await embeddings_model.aembed_documents(chunks)


async def create_query_embedding(query: str) -> list[float]:
    return await embeddings_model.aembed_query(query)
