# 취업준비 도움 챗봇

Gradio 기반 공통 애플리케이션 뼈대입니다. 프로필 온보딩 후 채팅 화면에서 **버튼으로 원하는 기능(Tool)을 직접 선택**하고, 그 안에서 자유롭게 질문합니다.

## Tool 선택 (버튼 기반, 자동 라우팅 없음)

| 버튼 | 기능 |
|---|---|
| 🧭 직무 추천 | 경험·역량에 맞는 직무 추천 |
| ✍️ 자소서 피드백 | 자소서 첨삭 |
| 🎤 면접 질문 | 예상 면접 질문 생성 |
| 🏅 자격증 추천 | 자격증·시험 일정 안내 |

이전엔 메시지 내용을 LLM/키워드로 분석해 Tool을 자동으로 골랐으나, **한 번 분류된 Tool이 다른 분야 질문에도 고정되는 문제**가 있었습니다. 지금은 사용자가 버튼을 눌러 명시적으로 Tool을 고정하고, 그 안에서는 입력한 메시지가 그대로 선택된 Tool의 `run()`으로 전달됩니다 — 어떤 Tool이 응답할지는 항상 버튼 선택으로만 결정됩니다.

## 모델 구조

| 용도 | 함수 (`core/llm.py`) | 모델 | 비고 |
|---|---|---|---|
| 콘텐츠 생성 | `get_generation_llm()` | `gpt-5.4` | 자소서·면접·직무 |
| RAG 임베딩 | `get_embeddings()` | `text-embedding-3-small` | |

`certificate`(자격증) Tool은 규칙기반이라 LLM을 쓰지 않습니다. Tool 선택은 LLM이 아니라 버튼 클릭으로 결정되므로 별도 라우팅 모델이 없습니다. 전체 구조는 `AGENTS.md` 참고.

자격증 추천은 SQLD·ADsP·투운사·정처기 등 국내 자격증과 TOEIC·OPIc·JLPT·HSK·TOPIK 등 어학시험(`data/raw/language_tests.json`)을 함께 검색하고, 시험 일정은 `ingest/certs/build_certs_data.py`로 공식 사이트에서 수집한 `data/raw/certs.json`을 기준으로 안내합니다(배포 앱은 실시간 크롤링하지 않음).

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

`render.yaml` 하나로 3개 서비스를 배포합니다(Render 대시보드 → New + → Blueprint → 이 repo 연결).

| 서비스 | 용도 | 환경변수 |
|---|---|---|
| `job-prep-chatbot` | Gradio 메인 앱 | `OPENAI_API_KEY` |
| `job-prep-chatbot-api` | FastAPI(`app/api.py`), vtuber가 호출 | `OPENAI_API_KEY`, (선택) `AZURE_SPEECH_KEY`/`AZURE_SPEECH_REGION` |
| `job-prep-chatbot-vtuber` | vtuber 정적 빌드 | `VITE_CHAT_API` — `job-prep-chatbot-api`의 실제 URL을 직접 입력 |

`sync: false`로 표시된 키는 Blueprint 적용 후 Render 대시보드에서 직접 입력해야 합니다.
`job-prep-chatbot-api`를 먼저 배포해 URL(예: `https://job-prep-chatbot-api.onrender.com`)을 확인한 뒤, 그 값을 `job-prep-chatbot-vtuber`의 `VITE_CHAT_API`에 입력하고 다시 배포하세요. Vite 빌드 시점에 값이 박히므로 API URL이 바뀌면 vtuber도 다시 배포해야 합니다.

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
