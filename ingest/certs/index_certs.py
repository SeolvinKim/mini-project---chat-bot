from __future__ import annotations

import json
from pathlib import Path

from langchain_core.documents import Document

ROOT = Path(__file__).resolve().parents[2]
DATA_PATHS = [
    ROOT / "data" / "raw" / "certs.json",
    ROOT / "data" / "raw" / "language_tests.json",
]


def build_documents() -> list[Document]:
    documents = []
    certificates = []
    for data_path in DATA_PATHS:
        if data_path.exists():
            payload = json.loads(data_path.read_text(encoding="utf-8"))
            certificates.extend(payload.get("certificates", []))
    for certificate in certificates:
        content = "\n".join(
            [
                f"자격증명: {certificate['certificate_name']}",
                f"분야: {certificate['category']}",
                f"관련 직무: {', '.join(certificate['related_jobs'])}",
                f"키워드: {', '.join(certificate['keywords'])}",
                f"설명: {certificate['description']}",
                f"시행기관: {certificate['source_name']}",
            ]
        )
        documents.append(
            Document(
                page_content=content,
                metadata={
                    "certificate_id": certificate["certificate_id"],
                    "certificate_name": certificate["certificate_name"],
                    "category": certificate["category"],
                    "source_url": certificate["source_url"],
                },
            )
        )
    return documents


def main() -> None:
    try:
        from core.vectorstore import get_vectorstore
    except ImportError as error:
        raise SystemExit(
            "통합자의 core/vectorstore.py가 필요합니다. "
            "팀 공통 코드가 합쳐진 뒤 다시 실행해 주세요."
        ) from error

    vectorstore = get_vectorstore("certs")
    documents = build_documents()
    ids = [f"cert:{doc.metadata['certificate_id']}" for doc in documents]

    try:
        vectorstore.delete(ids=ids)
    except Exception:
        pass
    vectorstore.add_documents(documents=documents, ids=ids)
    print(f"certs 컬렉션에 {len(documents)}개 문서를 적재했습니다.")


if __name__ == "__main__":
    main()
