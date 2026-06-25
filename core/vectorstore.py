from functools import lru_cache
from pathlib import Path

from langchain_chroma import Chroma

from core.llm import get_embeddings

CHROMA_PATH = Path(__file__).resolve().parents[1] / "chroma_db"


@lru_cache(maxsize=8)
def get_vectorstore(collection_name: str) -> Chroma:
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=collection_name,
        embedding_function=get_embeddings(),
        persist_directory=str(CHROMA_PATH),
    )
