"""vtuber 캐릭터(또는 외부 클라이언트)가 호출하는 HTTP API.

- POST /api/chat : 메시지를 알맞은 Tool로 보내 답변 텍스트를 만든다.
- POST /api/tts  : 답변 텍스트를 OpenAI TTS로 mp3 합성해 돌려준다.
- GET  /api/tools: 사용 가능한 Tool 목록(프론트의 선택 UI용).

설계 메모
---------
이 파일은 의도적으로 ``app.main``(Gradio 셸)을 import하지 않는다.
- main.py는 import 시 Gradio Blocks를 통째로 빌드한다(API 서버엔 불필요).
- main.py는 별도 세션에서 활발히 수정 중이라, 그 내부 함수에 의존하면 깨지기 쉽다.
그래서 Tool 레지스트리와 로더를 여기서 자체 보유하고, 공유 계약인
``core.schema.UserProfile`` 과 각 Tool의 ``run(profile, user_input)`` 만 사용한다.

Gradio 앱과 별개 프로세스로 띄운다:
    uv run uvicorn app.api:app --port 8000
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.schema import UserProfile

load_dotenv()

# ---------------------------------------------------------------------------
# Tool 레지스트리 (app/main.py의 TOOLS와 동일한 key/module을 의도적으로 미러링)
# ---------------------------------------------------------------------------
TOOLS: tuple[tuple[str, str, str, str], ...] = (
    # (key, module, label, icon)
    ("job", "tools.recommend_job", "직무 추천", "🧭"),
    ("cover_letter", "tools.cover_letter", "자소서 피드백", "✍️"),
    ("interview", "tools.interview", "면접 질문", "🎤"),
    ("certificate", "tools.spec_recommend", "자격증 추천", "🏅"),
)
TOOL_MAP = {key: (module, label, icon) for key, module, label, icon in TOOLS}
DEFAULT_TOOL = TOOLS[0][0]

# 클라이언트가 tool을 지정하지 않았을 때만 쓰는 가벼운 키워드 분류(폴백).
KEYWORD_GROUPS: dict[str, tuple[str, ...]] = {
    "certificate": ("자격증", "시험 일정", "원서접수", "sqld", "adsp", "투운사", "정처기", "컴활", "기사 시험"),
    "cover_letter": ("자소서", "자기소개서", "지원동기", "첨삭", "문장 수정", "글자 수", "star"),
    "interview": ("면접", "예상 질문", "압박 질문", "답변 연습", "면접관"),
    "job": ("직무", "진로", "적성", "어떤 일", "무슨 일", "취업 분야", "직업 추천"),
}

# TTS 모델/보이스는 환경변수로 교체 가능. tts-1 은 실재하는 OpenAI TTS 모델.
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")
TTS_VOICE = os.getenv("TTS_VOICE", "alloy")
TTS_MAX_CHARS = 4000  # OpenAI TTS 입력 길이 안전 상한


def _load_run(tool_key: str) -> Callable[[UserProfile, str], str] | None:
    module_path = TOOL_MAP[tool_key][0]
    try:
        module = importlib.import_module(module_path)
        return getattr(module, "run")
    except (ImportError, AttributeError):
        return None


def _keyword_route(message: str) -> str | None:
    normalized = message.lower()
    for tool, keywords in KEYWORD_GROUPS.items():
        if any(keyword in normalized for keyword in keywords):
            return tool
    return None


app = FastAPI(title="job-prep-chatbot API")

# 개발 단계에서는 모든 origin 허용. 배포 시 vtuber origin으로 좁힌다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProfileIn(BaseModel):
    session_id: str = ""
    education: str = ""
    target_job: str = ""
    skills: list[str] = Field(default_factory=list)
    experiences: list[str] = Field(default_factory=list)
    certs: list[str] = Field(default_factory=list)


class ChatIn(BaseModel):
    message: str
    # 명시하면 해당 Tool로 직행, None이면 키워드 폴백 분류.
    tool: str | None = None
    profile: ProfileIn = Field(default_factory=ProfileIn)


class ChatOut(BaseModel):
    text: str
    tool: str
    label: str


class TTSIn(BaseModel):
    text: str
    voice: str | None = None


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/tools")
def tools() -> list[dict[str, str]]:
    return [{"key": k, "label": label, "icon": icon} for k, _, label, icon in TOOLS]


@app.post("/api/chat", response_model=ChatOut)
def chat(body: ChatIn) -> ChatOut:
    message = (body.message or "").strip()
    if not message:
        return ChatOut(text="질문을 입력해 주세요.", tool="", label="")

    tool_key = body.tool if body.tool in TOOL_MAP else _keyword_route(message)
    if tool_key is None:
        return ChatOut(
            text=(
                "어떤 준비를 도와드릴까요? 직무 추천, 자소서 피드백, 면접 질문, "
                "자격증 중에서 편하게 말씀해 주세요."
            ),
            tool="",
            label="일반 대화",
        )

    _, label, _icon = TOOL_MAP[tool_key]
    run = _load_run(tool_key)
    if run is None:
        text = f"질문은 {label}에 해당하지만 아직 해당 Tool이 준비되지 않았어요."
    else:
        profile = UserProfile(**body.profile.model_dump())
        try:
            text = str(run(profile, message))
        except Exception:
            text = "요청을 처리하지 못했어요. 입력을 확인하고 다시 시도해 주세요."

    return ChatOut(text=text, tool=tool_key, label=label)


@app.post("/api/tts")
def tts(body: TTSIn) -> Response:
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty text")
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not set")

    from openai import OpenAI

    client = OpenAI()
    try:
        with client.audio.speech.with_streaming_response.create(
            model=TTS_MODEL,
            voice=body.voice or TTS_VOICE,
            input=text[:TTS_MAX_CHARS],
        ) as response:
            audio = response.read()
    except Exception:
        raise HTTPException(status_code=502, detail="tts failed")

    return Response(content=audio, media_type="audio/mpeg")
