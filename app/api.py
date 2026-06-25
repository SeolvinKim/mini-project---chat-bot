"""vtuber 캐릭터(또는 외부 클라이언트)가 호출하는 HTTP API.

- POST /api/chat : 메시지를 알맞은 Tool로 보내 답변 텍스트를 만든다.
- POST /api/tts  : 답변 텍스트를 음성(mp3)으로 합성해 돌려준다.
                   기본은 Azure Speech(한국 여성 음성 + SSML), 실패하면 OpenAI TTS로 폴백.
- GET  /api/tools: 사용 가능한 Tool 목록(프론트의 선택 UI용).
- GET  /api/voices: 선택 가능한 한국 여성 음성 후보(프론트 드롭다운용).

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
import re
import sys
from pathlib import Path
from typing import Callable
from xml.sax.saxutils import escape, quoteattr

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

# ---------------------------------------------------------------------------
# TTS 설정
# ---------------------------------------------------------------------------
# provider 우선순위: 기본은 azure 먼저 시도하고 실패하면 openai로 폴백한다.
# TTS_PROVIDER=openai 로 두면 순서가 뒤집힌다.
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "azure").strip().lower()
TTS_MAX_CHARS = 4000  # 입력 길이 안전 상한

# --- OpenAI TTS ---
OPENAI_TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")  # tts-1 은 실재하는 OpenAI TTS 모델
OPENAI_TTS_VOICE = os.getenv("TTS_VOICE", "alloy")
OPENAI_VOICES = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}

# --- Azure Speech TTS ---
# 키 발급: Azure Portal > "Speech service" 리소스 생성 > 키와 위치(region).
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "koreacentral")
AZURE_TTS_VOICE = os.getenv("AZURE_TTS_VOICE", "ko-KR-SunHiNeural")
# 차분·부드러운 내레이션 톤(요청 SSML 반영). prosody 는 모든 음성에서 동작한다.
AZURE_TTS_RATE = os.getenv("AZURE_TTS_RATE", "-12%")
AZURE_TTS_PITCH = os.getenv("AZURE_TTS_PITCH", "-8%")
# mstts:express-as 스타일은 "지원하는 음성"에서만 동작한다(ko-KR 표준 음성은 대부분 미지원).
# 미지원 음성에 스타일을 넣으면 합성이 통째로 실패하므로 기본은 비활성(빈 값)으로 둔다.
AZURE_TTS_STYLE = os.getenv("AZURE_TTS_STYLE", "")
AZURE_TTS_STYLEDEGREE = os.getenv("AZURE_TTS_STYLEDEGREE", "")

# 프론트 드롭다운/데모용 한국 여성 음성 후보.
KO_FEMALE_VOICES: tuple[str, ...] = (
    "ko-KR-SunHiNeural",
    "ko-KR-JiMinNeural",
    "ko-KR-SeoHyeonNeural",
    "ko-KR-SoonBokNeural",
    "ko-KR-YuJinNeural",
)


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


CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")

_SYSTEM_PROMPT = (
    "당신은 취업 준비를 돕는 친절한 AI 어시스턴트입니다. "
    "직무 추천, 자기소개서 피드백, 면접 준비, 자격증 추천을 전문으로 합니다. "
    "한국어로 간결하고 실용적으로 답하세요."
)


def _general_chat(message: str, history: list) -> str:
    """키워드 분류에 걸리지 않은 일반 대화를 GPT로 처리. API 키 없으면 안내 문구 반환."""
    if not os.getenv("OPENAI_API_KEY"):
        return (
            "어떤 준비를 도와드릴까요? 직무 추천, 자소서 피드백, 면접 질문, "
            "자격증 중에서 편하게 말씀해 주세요."
        )

    from openai import OpenAI

    client = OpenAI()
    messages: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for h in history[-8:]:  # 최근 8개 메시지만 컨텍스트로
        role = h.role if hasattr(h, "role") else h.get("role", "")
        content = h.content if hasattr(h, "content") else h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    try:
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=600,
        )
        return resp.choices[0].message.content or "응답을 생성하지 못했어요."
    except Exception:
        return (
            "어떤 준비를 도와드릴까요? 직무 추천, 자소서 피드백, 면접 질문, "
            "자격증 중에서 편하게 말씀해 주세요."
        )


def _make_tts_text(full: str) -> str:
    """TTS용 핵심 1~2문장 요약. API 키 없거나 텍스트가 짧으면 첫 문장 추출로 폴백."""
    clean = re.sub(r'[#*_`~>]', '', full)
    clean = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', clean)
    clean = re.sub(r'^\s*\|.*', '', clean, flags=re.MULTILINE)
    clean = re.sub(r'\s+', ' ', clean).strip()

    def first_sentence(text: str, limit: int = 120) -> str:
        parts = re.split(r'(?<=[.!?])\s+', text)
        return parts[0][:limit] if parts else text[:limit]

    if len(clean) < 60 or not os.getenv("OPENAI_API_KEY"):
        return first_sentence(clean)

    from openai import OpenAI

    try:
        resp = OpenAI().chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "TTS로 읽을 핵심 1~2문장(50자 이내)으로 요약하세요. 존댓말, 마크다운 없이.",
                },
                {"role": "user", "content": clean[:800]},
            ],
            max_tokens=70,
        )
        return resp.choices[0].message.content or first_sentence(clean)
    except Exception:
        return first_sentence(clean)


# ---------------------------------------------------------------------------
# 음성 합성 (Azure 우선, OpenAI 폴백)
# ---------------------------------------------------------------------------
def build_ssml(
    text: str,
    voice: str,
    *,
    style: str = "",
    styledegree: str = "",
    rate: str = "",
    pitch: str = "",
) -> str:
    """Azure Speech용 SSML 문자열을 만든다.

    - prosody(rate/pitch)는 모든 음성에서 동작한다.
    - mstts:express-as(style)는 해당 음성이 지원할 때만 감싼다.
    - 텍스트는 XML 이스케이프해 SSML 깨짐/인젝션을 막는다.
    """
    inner = escape(text)
    if rate or pitch:
        attrs = ""
        if rate:
            attrs += f" rate={quoteattr(rate)}"
        if pitch:
            attrs += f" pitch={quoteattr(pitch)}"
        inner = f"<prosody{attrs}>{inner}</prosody>"
    if style:
        degree = f" styledegree={quoteattr(styledegree)}" if styledegree else ""
        inner = f"<mstts:express-as style={quoteattr(style)}{degree}>{inner}</mstts:express-as>"
    return (
        '<speak version="1.0"'
        ' xmlns="http://www.w3.org/2001/10/synthesis"'
        ' xmlns:mstts="https://www.w3.org/2001/mstts"'
        ' xml:lang="ko-KR">'
        f"<voice name={quoteattr(voice)}>{inner}</voice>"
        "</speak>"
    )


def azure_tts(text: str, voice: str | None = None) -> bytes:
    """Azure Speech로 한국어 음성을 mp3 bytes로 합성한다. 키/리전 없으면 RuntimeError."""
    if not (AZURE_SPEECH_KEY and AZURE_SPEECH_REGION):
        raise RuntimeError("AZURE_SPEECH_KEY/AZURE_SPEECH_REGION not set")

    import azure.cognitiveservices.speech as speechsdk

    cfg = speechsdk.SpeechConfig(
        subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION
    )
    cfg.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
    )
    # audio_config=None → 스피커로 재생하지 않고 결과를 메모리(bytes)로 받는다.
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)
    ssml = build_ssml(
        text,
        voice or AZURE_TTS_VOICE,
        style=AZURE_TTS_STYLE,
        styledegree=AZURE_TTS_STYLEDEGREE,
        rate=AZURE_TTS_RATE,
        pitch=AZURE_TTS_PITCH,
    )
    result = synthesizer.speak_ssml_async(ssml).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return bytes(result.audio_data)

    detail = "unknown"
    if result.reason == speechsdk.ResultReason.Canceled:
        cancellation = result.cancellation_details
        detail = f"{cancellation.reason}: {cancellation.error_details}"
    raise RuntimeError(f"azure synth failed ({detail})")


def openai_tts(text: str, voice: str | None = None) -> bytes:
    """OpenAI TTS로 음성을 mp3 bytes로 합성한다. 키 없으면 RuntimeError."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY not set")

    from openai import OpenAI

    selected = voice if voice in OPENAI_VOICES else OPENAI_TTS_VOICE
    client = OpenAI()
    with client.audio.speech.with_streaming_response.create(
        model=OPENAI_TTS_MODEL,
        voice=selected,
        input=text[:TTS_MAX_CHARS],
    ) as response:
        return response.read()


def synthesize(text: str, voice: str | None = None) -> tuple[bytes, str]:
    """TTS_PROVIDER 순서대로 시도해 (audio_bytes, used_provider)를 반환한다.

    Azure 음성명(ko-KR-*)이 들어오면 Azure에서만 의미가 있으므로 그쪽으로 라우팅한다.
    모든 provider가 실패하면 마지막 오류 메시지를 합쳐 RuntimeError를 던진다.
    """
    order = ["azure", "openai"] if TTS_PROVIDER != "openai" else ["openai", "azure"]
    errors: list[str] = []
    for provider in order:
        try:
            if provider == "azure":
                azure_voice = voice if (voice or "").startswith("ko-KR-") else None
                return azure_tts(text, azure_voice), "azure"
            openai_voice = voice if voice in OPENAI_VOICES else None
            return openai_tts(text, openai_voice), "openai"
        except Exception as error:  # 다음 provider로 폴백
            errors.append(f"{provider}: {error}")
    raise RuntimeError("; ".join(errors) or "no tts provider available")


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


class HistoryMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatIn(BaseModel):
    message: str
    # 명시하면 해당 Tool로 직행, None이면 키워드 폴백 분류.
    tool: str | None = None
    profile: ProfileIn = Field(default_factory=ProfileIn)
    # 이전 대화 기록 (일반 대화에서 GPT 컨텍스트로 활용)
    history: list[HistoryMessage] = Field(default_factory=list)


class ChatOut(BaseModel):
    text: str
    tts_text: str  # TTS용 핵심 요약 (채팅 버블엔 text, 음성엔 tts_text)
    tool: str
    label: str


class TTSIn(BaseModel):
    text: str
    # "ko-KR-SunHiNeural" 같은 Azure 음성명 또는 "alloy" 같은 OpenAI 음성명.
    voice: str | None = None


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/tools")
def tools() -> list[dict[str, str]]:
    return [{"key": k, "label": label, "icon": icon} for k, _, label, icon in TOOLS]


@app.get("/api/voices")
def voices() -> dict[str, object]:
    """프론트 드롭다운용: 기본 음성과 한국 여성 음성 후보 목록."""
    return {
        "provider": TTS_PROVIDER,
        "default": AZURE_TTS_VOICE,
        "candidates": list(KO_FEMALE_VOICES),
    }


@app.post("/api/chat", response_model=ChatOut)
def chat(body: ChatIn) -> ChatOut:
    message = (body.message or "").strip()
    if not message:
        return ChatOut(text="질문을 입력해 주세요.", tts_text="질문을 입력해 주세요.", tool="", label="")

    tool_key = body.tool if body.tool in TOOL_MAP else _keyword_route(message)
    if tool_key is None:
        text = _general_chat(message, body.history)
        return ChatOut(text=text, tts_text=_make_tts_text(text), tool="", label="일반 대화")

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

    return ChatOut(text=text, tts_text=_make_tts_text(text), tool=tool_key, label=label)


@app.post("/api/tts")
def tts(body: TTSIn) -> Response:
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty text")

    try:
        audio, provider = synthesize(text[:TTS_MAX_CHARS], body.voice)
    except Exception as error:
        # Azure/OpenAI 모두 실패(키 미설정 포함) → 503. 내부 상세는 detail에만.
        raise HTTPException(status_code=503, detail=str(error))

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"X-TTS-Provider": provider},
    )
