import os
from functools import lru_cache

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

ROUTER_MODEL = os.getenv("OPENAI_ROUTER_MODEL", "gpt-5.4-mini")
GENERATION_MODEL = os.getenv("OPENAI_GENERATION_MODEL", "gpt-5.4")


@lru_cache(maxsize=1)
def get_router_llm() -> ChatOpenAI:
    """질문 문맥을 분석해 Tool을 선택하는 빠른 라우터 모델."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
    return ChatOpenAI(
        model=ROUTER_MODEL,
        temperature=0,
        timeout=20,
        max_retries=1,
    )


@lru_cache(maxsize=1)
def get_generation_llm() -> ChatOpenAI:
    """자소서 피드백·면접 질문 등 콘텐츠를 생성하는 Tool용."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
    return ChatOpenAI(model=GENERATION_MODEL, temperature=0.3, timeout=60, max_retries=1)


@lru_cache(maxsize=1)
def get_embeddings() -> OpenAIEmbeddings:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
    return OpenAIEmbeddings(model="text-embedding-3-small")
