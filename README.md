# 취업준비 챗봇 Tool 4 — 자격증 추천

금융·데이터·IT·디지털 직무에 맞는 자격증을 추천하고, 저장된 공식 자료를 바탕으로 2026년 시험 일정을 안내합니다.

## 주요 기능

- 희망 직무 기반 자격증 최대 3개 추천
- `SQLD`, `ADsP`, `투운사`, `정처기` 등 약칭 인식
- 올해 예정 시험과 종료 시험 구분
- 접수 기간, 시험일, 합격자 발표일 표시
- 공식 출처와 데이터 기준일 표시
- Chroma `certs` 컬렉션이 없을 때 키워드 방식으로 자동 폴백

## 로컬 실행

```bash
uv sync
uv run python ingest/certs/build_certs_data.py
uv run pytest
uv run python demo_app.py
```

브라우저에서 `http://localhost:7860`으로 접속합니다.

## 팀 통합

통합 챗봇에서는 다음 함수만 사용합니다.

```python
from tools.spec_recommend import NAME, run
```

```python
result = run(profile, "SQLD 올해 시험 일정 알려줘")
```

`profile`은 팀 공통 `core.schema.UserProfile` 객체이며 Tool 내부에서 수정하지 않습니다.

RAG 인덱싱은 통합자의 `core/vectorstore.py`가 준비된 뒤 실행합니다.

```bash
uv run python ingest/certs/index_certs.py
```

## 데이터 갱신

```bash
uv run python ingest/certs/build_certs_data.py
```

- 데이터자격시험과 금융투자협회의 공개 연간 일정을 수집합니다.
- 다른 시행기관 자격증은 공식 링크와 추천 메타데이터를 제공하며, 일정 데이터가 없으면 공식 사이트 확인을 안내합니다.
- 배포 앱에서는 실시간 크롤링하지 않습니다.

## Render

저장소에 포함된 `render.yaml`을 이용해 Web Service를 만들 수 있습니다.

- Build: `pip install uv && uv sync --frozen`
- Start: `uv run python demo_app.py`
- 환경변수: `OPENAI_API_KEY`

`OPENAI_API_KEY`가 없어도 키워드 기반 추천과 일정 조회는 동작합니다.
