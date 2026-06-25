import os
from functools import lru_cache

from langchain_openai import ChatOpenAI, OpenAIEmbeddings


@lru_cache(maxsize=1)
def get_llm() -> ChatOpenAI:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
        timeout=20,
        max_retries=1,
    )


@lru_cache(maxsize=1)
def get_embeddings() -> OpenAIEmbeddings:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
    return OpenAIEmbeddings(model="text-embedding-3-small")
