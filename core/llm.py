import os
from functools import lru_cache

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

# 역할별 모델 분리 (자세한 구조는 README.md / AGENTS.md 참고)
# - 라우팅(분류): 빠르고 저렴한 mini. 키워드로 안 될 때만 호출.
# - 생성(자소서·면접·직무 등): 품질 우선 모델.
ROUTER_MODEL = "gpt-5.4-mini"
GENERATION_MODEL = "gpt-5.4"


@lru_cache(maxsize=1)
def get_router_llm() -> ChatOpenAI:
    """어떤 Tool로 보낼지 분류하는 라우터용. 결정적이도록 temperature=0."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
    return ChatOpenAI(model=ROUTER_MODEL, temperature=0, timeout=20, max_retries=1)


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
