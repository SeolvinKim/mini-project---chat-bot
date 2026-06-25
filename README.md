# 취업준비 도움 챗봇

Gradio 기반 공통 애플리케이션 뼈대입니다. 프로필 온보딩 후 4개 Tool을 하나의 채팅 화면에서 선택해 사용할 수 있습니다.

## Tool 파일

| 기능 | 파일 |
|---|---|
| 직무 추천 | `tools/recommend_job.py` |
| 자소서 피드백 | `tools/cover_letter.py` |
| 면접 질문 | `tools/interview.py` |
| 자격증 추천 | `tools/spec_recommend.py` |

각 파일은 `NAME`과 `run(profile, user_input) -> str`을 제공합니다. 아직 병합되지 않은 Tool은 화면에서 준비 중으로 안내됩니다.

## 실행

```powershell
uv sync
Copy-Item .env.example .env
uv run python app/main.py
```

[http://localhost:7860](http://localhost:7860)으로 접속합니다.

`.env`의 `OPENAI_API_KEY`에 키를 입력하면 최근 대화를 참고해
`그 자격증 일정 알려줘` 같은 후속 질문을 독립된 질문으로 정리한 뒤 Tool에 전달합니다.
키가 없거나 호출에 실패하면 기존 규칙 기반 방식으로 계속 동작합니다.

## Render

- Build: `pip install uv && uv sync --frozen`
- Start: `uv run python app/main.py`
- 환경변수: `OPENAI_API_KEY`
