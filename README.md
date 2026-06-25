# 취업준비 도움 챗봇

Gradio 기반 취업준비 챗봇입니다. 프로필 온보딩 후 하나의 채팅창에서 질문하면 알맞은 Tool로 자동 연결합니다.

UI는 `assets/fonts/ChironGoRoundTC-VariableFont_wght.ttf`를 전체 화면 글꼴로 사용하며,
반투명 리퀴드 글래스 카드·버튼과 모바일 대응형 시험 일정 카드로 구성됩니다.

## 자동 Tool 라우팅

| 질문 예시 | 연결 기능 |
|---|---|
| 내 경험에 맞는 금융권 직무를 추천해줘 | 직무 추천 |
| 이 자소서 지원동기를 피드백해줘 | 자소서 피드백 |
| 데이터 분석 직무 면접 질문을 만들어줘 | 면접 질문 |
| SQLD 올해 시험 일정 알려줘 | 자격증 추천·일정 |

명확한 질문은 키워드로 빠르게 분류하고, 모호한 질문과 후속 질문은 LLM이 최근 대화와 프로필을 참고해 분류합니다. API 키가 없을 때도 키워드 기반 기본 라우팅은 동작합니다.

## 모델 구조

| 용도 | 함수 (`core/llm.py`) | 모델 | 비고 |
|---|---|---|---|
| 질문 라우팅 | `get_router_llm()` | `gpt-5.4-mini` | 모호한 질문에만 사용 |
| 콘텐츠 생성 | `get_generation_llm()` | `gpt-5.4` | 자소서·면접·직무 |
| RAG 임베딩 | `get_embeddings()` | `text-embedding-3-small` | |

`certificate`(자격증) Tool은 규칙기반으로 답변하며, LLM은 필요한 경우 질문의 의도를 분류하는 데만 사용합니다.

## Tool 파일

| 기능 | 파일 |
|---|---|
| 직무 추천 | `tools/recommend_job.py` |
| 자소서 피드백 | `tools/cover_letter.py` |
| 면접 질문 | `tools/interview.py` |
| 자격증 추천 | `tools/spec_recommend.py` |

각 파일은 `NAME`과 `run(profile, user_input) -> str`을 제공합니다. 아직 병합되지 않은 Tool은 화면에서 준비 중으로 안내됩니다.

### Tool 작성 계약 (중요)

`run`이 받는 `profile`(`core.schema.UserProfile`)에는 **`session_id`** 필드가 있습니다.
`app/main.py`가 Gradio 세션 해시를 주입한 값으로, **사용자(브라우저 세션)마다 고유**합니다.

- Tool이 사용자별 상태(추천 이력, 대화 단계 등)를 모듈 전역에 보관한다면 **반드시 `profile.session_id`로 키를 잡으세요.**
- 프로필 *내용*(학력·직무 등)으로 키를 잡으면 **동일 프로필을 입력한 다른 사용자끼리 상태가 충돌**합니다.
- 예시: `tools/spec_recommend.py`의 `_profile_key()` — `session_id`가 있으면 `session:<id>`를 키로 사용.

```python
# 사용자별 상태가 필요할 때
key = profile.session_id or "_anon"   # 폴백
STATE[key] = ...
```

## 실행

```powershell
uv sync
Copy-Item .env.example .env
uv run python app/main.py
```

[http://localhost:7860](http://localhost:7860)으로 접속합니다.

`.env`의 `OPENAI_API_KEY`에 발급받은 키를 입력합니다. `.env` 파일은 GitHub에 올리지 않습니다.

## Render

- Build: `pip install uv && uv sync --frozen`
- Start: `uv run python app/main.py`
- 환경변수: `OPENAI_API_KEY`

## vtuber (VRM 아바타 프론트엔드)

`vtuber/`는 웹캠 모션 트래킹 + VRM 아바타가 `app/api.py`(FastAPI)와 HTTP로 통신하는 별도 Vite 프로젝트입니다. `POST /api/chat`으로 답변을 받고 `POST /api/tts`로 음성을 합성해 립싱크합니다.

```powershell
# 1) API 서버 (별도 터미널)
uv run uvicorn app.api:app --port 8000

# 2) 프론트엔드
cd vtuber
npm install
Copy-Item .env.example .env   # 필요 시 VITE_CHAT_API 수정
npm run dev
```

[http://localhost:5173](http://localhost:5173)으로 접속합니다. (Gradio 앱의 7860과는 별개 화면입니다.)
