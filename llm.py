from langchain_openai import ChatOpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL


def get_llm(model_name):
    kwargs = {
        "model": model_name,
        "temperature": 0,
        "api_key": OPENAI_API_KEY,
    }

    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL

    return ChatOpenAI(**kwargs)