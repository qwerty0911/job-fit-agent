from langchain_openai import OpenAIEmbeddings

from config import OPENAI_API_KEY


embeddings_model = OpenAIEmbeddings(
    model="text-embedding-3-large",
    api_key=OPENAI_API_KEY,
)

