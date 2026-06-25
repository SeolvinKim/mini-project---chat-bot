# 취업준비 도움 챗봇

Gradio 기반 공통 애플리케이션 뼈대입니다. 프로필 온보딩 후 하나의 채팅창에서 질문하면, 질문의 의도를 파악해 알맞은 Tool로 자동 연결합니다.

## 자동 Tool 라우팅

| 질문 예시 | 연결 기능 |
|---|---|
| 데이터 분석가와 잘 맞는 직무를 추천해줘 | 직무 추천 |
| 이 자기소개서 문장을 다듬어줘 | 자소서 피드백 |
| 은행 면접 질문을 만들어줘 | 면접 질문 |
| SQLD 올해 시험 일정 알려줘 | 자격증 추천·일정 |

`OPENAI_API_KEY`가 있으면 LLM이 최근 대화와 프로필까지 참고해 문맥을 분류하고, `그 자격증 일정도 알려줘` 같은 후속 질문을 독립된 요청으로 정리합니다. API 호출이 불가능한 경우에는 키워드 기반 분류로 기본 기능을 계속 사용할 수 있습니다.

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
