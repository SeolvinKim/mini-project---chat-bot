import os
from functools import lru_cache

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

# Tool 선택은 버튼으로 사용자가 직접 한다 (app/main.py select_tool) — LLM 라우팅 없음.
# 생성(자소서·면접·직무 등)에만 품질 우선 모델을 쓴다.
GENERATION_MODEL = "gpt-5.4"


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
