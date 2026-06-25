# AGENTS.md

코딩 에이전트(Codex / Claude Code 등)와 팀원이 이 저장소에서 지켜야 할 규칙.

## 환경

- 패키지/실행: `uv` 사용. 단독 `python` 호출 금지.
  - 설치: `uv sync`
  - 실행: `uv run python app/main.py`
  - 테스트: `uv run python -m pytest`
- Python 3.11~3.12.
- API 키: `OPENAI_API_KEY`(생성·임베딩). `.env.example` 참고.

## Tool 자동 라우팅 구조

```
사용자 입력
  │
  ▼
[빠른 분류] 명확한 키워드가 있으면 즉시 Tool 결정
  │
  ├─ 모호한 질문 → get_router_llm()이 최근 대화·프로필 참고
  ▼
[대답 생성] 선택된 Tool의 run(profile, message) 호출
  ├─ certificate : 규칙기반 (LLM 불필요)
  ├─ cover_letter: 생성 LLM 필요 → get_generation_llm() (미병합)
  ├─ interview   : 생성 LLM 필요 → get_generation_llm() (미병합)
  └─ job         : 생성 LLM 필요 → get_generation_llm() (미병합)
```

`core/llm.py` 헬퍼:

| 함수 | 모델 | 용도 |
|---|---|---|
| `get_router_llm()` | `gpt-5.4-mini` | 모호한 질문의 Tool 분류 |
| `get_generation_llm()` | `gpt-5.4` | 콘텐츠 생성 (자소서·면접·직무) |
| `get_embeddings()` | `text-embedding-3-small` | RAG 임베딩 |

- **생성 Tool은 `get_generation_llm()`을 쓰세요.**
- 키워드로 분류되지 않는 질문만 `get_router_llm()`을 사용합니다.

## 구조

- `app/main.py` — Gradio 셸. 온보딩 → 채팅. `TOOLS` 레지스트리로 4개 Tool을 동적 로딩.
- `app/api.py` — FastAPI HTTP API (`/api/chat`, `/api/tts`). `vtuber/` 프론트엔드가 호출. `app/main.py`와 별도 프로세스(`uv run uvicorn app.api:app --port 8000`).
- `core/` — 공유 인프라 (`schema.py`, `base.py`, `llm.py`, `vectorstore.py`).
- `tools/<name>.py` — 기능별 Tool. 각자 `NAME`과 `run(profile, user_input) -> str` 제공.
- `data/raw/certs.json` — 자격증/시험일정 데이터.
- `vtuber/` — Vite/three.js VRM 아바타 프론트엔드. `npm install && npm run dev` (포트 5173), `app/api.py`를 8000에 띄운 상태여야 응답한다. 자세한 실행법은 README.md 참고.

## Tool 작성 계약 ⚠️ 반드시 준수

`run(profile, user_input)`의 `profile`은 `core.schema.UserProfile`이며 **`session_id`** 필드를 가진다.

- `session_id`는 `app/main.py`가 주입하는 **Gradio 세션(브라우저 연결)별 고유 ID**다.
- Tool이 사용자별 상태(추천 이력, 대화 단계 등)를 **모듈 전역에 보관한다면 반드시 `profile.session_id`로 키를 잡아라.**
- 프로필 *내용*(학력·직무 등)으로 키를 잡지 마라 → 동일 프로필 입력 사용자끼리 상태가 충돌한다.

```python
def run(profile, user_input):
    key = profile.session_id or "_anon"   # 사용자별 상태 키
    ...
```

참고 구현: `tools/spec_recommend.py`의 `_profile_key()` / `_remember()` / `_already_recommended()`.

## 규칙

- 변경 후 `uv run python -m pytest`로 회귀 검증하고 결과 보고. 추측 금지.
- `core/`의 기존 인터페이스(`UserProfile`, `Tool` Protocol)를 임의로 바꾸지 마라. 바꿔야 하면 README/AGENTS.md도 함께 갱신.
- 최소 변경 원칙: 요청 범위 밖 리팩토링·서식 변경 금지.
