"""vtuber 캐릭터(또는 외부 클라이언트)가 호출하는 HTTP API.

- POST /api/chat : 기존 라우팅(app/main.py)을 그대로 재사용해 답변 텍스트를 만든다.
- POST /api/tts  : 답변 텍스트를 OpenAI TTS로 mp3 합성해 돌려준다.

Gradio 앱(app/main.py)과 별개 프로세스로 띄운다:
    uv run uvicorn app.api:app --port 8000
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

# 라우팅/Tool 실행 로직은 app/main.py 단일 소스를 그대로 재사용한다.
from app.main import TOOL_MAP, _load_run, _route_message
from core.schema import UserProfile

load_dotenv()

# TTS 모델/보이스는 환경변수로 교체 가능. tts-1 은 실재하는 OpenAI TTS 모델.
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")
TTS_VOICE = os.getenv("TTS_VOICE", "alloy")
TTS_MAX_CHARS = 4000  # OpenAI TTS 입력 길이 안전 상한

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
    history: list[dict] = Field(default_factory=list)
    profile: ProfileIn = Field(default_factory=ProfileIn)
    previous_tool: str = ""


class ChatOut(BaseModel):
    text: str
    tool: str
    route_status: str


class TTSIn(BaseModel):
    text: str
    voice: str | None = None


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/api/chat", response_model=ChatOut)
def chat(body: ChatIn) -> ChatOut:
    message = (body.message or "").strip()
    if not message:
        return ChatOut(text="질문을 입력해 주세요.", tool=body.previous_tool, route_status="")

    profile = UserProfile(**body.profile.model_dump())
    decision = _route_message(message, body.history, profile, body.previous_tool)

    if decision.tool == "general":
        text = decision.assistant_reply or "직무, 자소서, 면접, 자격증 중 무엇을 도와드릴까요?"
        return ChatOut(text=text, tool=body.previous_tool, route_status="💬 일반 대화")

    spec = TOOL_MAP[decision.tool]
    run = _load_run(spec)
    if run is None:
        text = (
            f"질문은 {spec.label}에 해당하지만 아직 해당 Tool이 준비되지 않았어요."
        )
    else:
        try:
            text = str(run(profile, decision.standalone_query or message))
        except Exception:
            text = "요청을 처리하지 못했어요. 입력을 확인하고 다시 시도해 주세요."

    return ChatOut(
        text=text,
        tool=decision.tool,
        route_status=f"{spec.icon} {spec.label}",
    )


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
