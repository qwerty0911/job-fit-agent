from langfuse.langchain import CallbackHandler

from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY


def create_langfuse_handler() -> CallbackHandler | None:
    """Create a request-scoped handler only when Langfuse credentials exist."""
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        return None

    return CallbackHandler()
