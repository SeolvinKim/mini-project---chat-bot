from __future__ import annotations

import importlib
import os
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import gradio as gr
from dotenv import load_dotenv
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.schema import UserProfile

load_dotenv()
FONT_PATH = ROOT / "assets" / "fonts" / "ChironGoRoundTC-VariableFont_wght.ttf"
if FONT_PATH.exists():
    gr.set_static_paths(FONT_PATH)


@dataclass(frozen=True)
class ToolSpec:
    key: str
    module: str
    label: str
    icon: str


TOOLS = (
    ToolSpec("job", "tools.recommend_job", "직무 추천", "🧭"),
    ToolSpec("cover_letter", "tools.cover_letter", "자소서 피드백", "✍️"),
    ToolSpec("interview", "tools.interview", "면접 질문", "🎤"),
    ToolSpec("certificate", "tools.spec_recommend", "자격증 추천", "🏅"),
)
TOOL_MAP = {tool.key: tool for tool in TOOLS}


class RouteDecision(BaseModel):
    tool: Literal["job", "cover_letter", "interview", "certificate", "general"]
    standalone_query: str
    assistant_reply: str = ""


def _split(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _profile_from_state(state: dict[str, object]) -> UserProfile:
    return UserProfile(
        session_id=str(state.get("session_id", "")),
        education=str(state.get("education", "")),
        target_job=str(state.get("target_job", "")),
        skills=list(state.get("skills", [])),
        experiences=list(state.get("experiences", [])),
        certs=list(state.get("certs", [])),
    )


def _load_run(spec: ToolSpec) -> Callable[[UserProfile, str], str] | None:
    try:
        module = importlib.import_module(spec.module)
        return getattr(module, "run")
    except (ImportError, AttributeError):
        return None


def enter_chat(
    education: str,
    target_job: str,
    skills: str,
    experiences: str,
    certs: str,
    request: gr.Request | None = None,
) -> tuple[dict[str, object], object, object, str, str]:
    # session_id는 Gradio 세션(브라우저 연결)별로 고유해야 사용자 간 Tool 상태가
    # 섞이지 않는다. request.session_hash가 표준 식별자이며, 없을 때만 uuid로 폴백.
    session_id = (request.session_hash if request and request.session_hash else None) or uuid.uuid4().hex
    profile = {
        "session_id": session_id,
        "education": (education or "").strip(),
        "target_job": (target_job or "").strip(),
        "skills": _split(skills),
        "experiences": _split(experiences),
        "certs": _split(certs),
    }
    summary = (
        f"**{profile['target_job'] or '희망 직무 미정'}**"
        f" · 기술 {', '.join(profile['skills']) or '미입력'}"
        f" · 보유 자격증 {', '.join(profile['certs']) or '없음'}"
    )
    return profile, gr.update(visible=False), gr.update(visible=True), summary, ""


def _extract_choices(answer: str) -> list[str]:
    choices = []
    for line in answer.splitlines():
        match = re.match(r"^#{0,3}\s*\d+\.\s*(.+?)\s*$", line.strip())
        if match:
            choices.append(re.sub(r"[*_`]", "", match.group(1)).strip())
    return choices[:5]


def _keyword_route(message: str, previous_tool: str = "") -> RouteDecision:
    normalized = message.lower()
    keyword_groups = {
        "certificate": (
            "자격증",
            "시험 일정",
            "원서접수",
            "sqld",
            "adsp",
            "투운사",
            "정처기",
            "컴활",
            "기사 시험",
        ),
        "cover_letter": (
            "자소서",
            "자기소개서",
            "지원동기",
            "첨삭",
            "문장 수정",
            "글자 수",
            "star 구조",
        ),
        "interview": (
            "면접",
            "예상 질문",
            "압박 질문",
            "답변 연습",
            "면접관",
        ),
        "job": (
            "직무",
            "진로",
            "적성",
            "어떤 일",
            "무슨 일",
            "취업 분야",
            "직업 추천",
        ),
    }
    for tool, keywords in keyword_groups.items():
        if any(keyword in normalized for keyword in keywords):
            return RouteDecision(tool=tool, standalone_query=message)
    greeting_only = normalized.strip(" !?.") in {
        "안녕",
        "안녕하세요",
        "반가워",
        "고마워",
        "감사합니다",
    }
    if previous_tool in TOOL_MAP and not greeting_only:
        return RouteDecision(tool=previous_tool, standalone_query=message)
    return RouteDecision(
        tool="general",
        standalone_query=message,
        assistant_reply=(
            "어떤 취업 준비를 도와드릴까요? "
            "직무 추천, 자소서 피드백, 면접 질문, 자격증 중 편하게 말씀해 주세요."
        ),
    )


def _route_message(
    message: str,
    history: list[dict[str, str]],
    profile: UserProfile,
    previous_tool: str = "",
) -> RouteDecision:
    if not os.getenv("OPENAI_API_KEY"):
        return _keyword_route(message, previous_tool)

    keyword_decision = _keyword_route(message, previous_tool)
    if keyword_decision.tool != "general":
        return keyword_decision

    recent = history[-6:]
    conversation = "\n".join(
        f"{item.get('role', 'user')}: {item.get('content', '')}" for item in recent
    )
    try:
        from core.llm import get_router_llm

        router = get_router_llm().with_structured_output(RouteDecision)
        return router.invoke(
            [
                (
                    "system",
                    "당신은 취업준비 챗봇의 라우터다. 사용자의 마지막 질문을 최근 대화와 "
                    "프로필을 참고해 정확히 하나로 분류한다.\n"
                    "- job: 적성, 진로, 직무 탐색과 직무 추천\n"
                    "- cover_letter: 자소서, 자기소개서, 지원동기 첨삭\n"
                    "- interview: 면접 질문, 답변 연습, 압박 면접\n"
                    "- certificate: 자격증 추천, 시험 일정, 접수일\n"
                    "- general: 인사, 잡담, 정보 부족 또는 위 네 기능에 속하지 않음\n"
                    "standalone_query에는 후속 표현을 풀어쓴 독립적인 한국어 질문을 작성한다. "
                    "사용자가 말하지 않은 사실·경험·날짜를 만들지 말고 고유명사를 보존한다. "
                    "general이면 assistant_reply에 친절한 짧은 답변 또는 필요한 추가 질문을 "
                    "작성하고, 그 외에는 assistant_reply를 빈 문자열로 둔다.",
                ),
                (
                    "human",
                    f"직전 Tool: "
                    f"{TOOL_MAP[previous_tool].label if previous_tool in TOOL_MAP else '없음'}\n"
                    f"희망 직무: {profile.target_job or '미입력'}\n"
                    f"최근 대화:\n{conversation or '없음'}\n"
                    f"마지막 질문: {message}",
                ),
            ]
        )
    except Exception:
        return _keyword_route(message, previous_tool)


def respond(
    message: str,
    history: list[dict[str, str]] | None,
    profile_state: dict[str, object],
    previous_tool: str,
) -> tuple[str, list[dict[str, str]], gr.Radio, str, str]:
    history = list(history or [])
    message = (message or "").strip()
    if not message:
        return "", history, gr.Radio(), previous_tool, ""

    profile = _profile_from_state(profile_state)
    decision = _route_message(message, history, profile, previous_tool)

    if decision.tool == "general":
        answer = decision.assistant_reply or (
            "직무, 자소서, 면접, 자격증 중 어떤 준비를 도와드릴까요?"
        )
        routed_tool = previous_tool
        route_status = "💬 일반 대화"
    else:
        spec = TOOL_MAP[decision.tool]
        run = _load_run(spec)
        routed_tool = decision.tool
        route_status = f"{spec.icon} **{spec.label}** 기능으로 연결했어요."
        if run is None:
            answer = (
                f"질문은 **{spec.label}**에 해당해요. "
                "아직 담당 Tool 코드가 `main`에 병합되지 않아 실행할 수 없습니다."
            )
        else:
            try:
                answer = str(run(profile, decision.standalone_query or message))
            except Exception:
                answer = "요청을 처리하지 못했어요. 입력을 확인하고 다시 시도해 주세요."

    history.extend(
        [{"role": "user", "content": message}, {"role": "assistant", "content": answer}]
    )
    choices = _extract_choices(answer)
    return (
        "",
        history,
        gr.Radio(choices=choices, value=None, visible=bool(choices)),
        routed_tool,
        route_status,
    )


def choose_follow_up(
    choice: str | None,
    history: list[dict[str, str]] | None,
    profile_state: dict[str, object],
    previous_tool: str,
) -> tuple[list[dict[str, str]], gr.Radio, str, str]:
    if not choice:
        return list(history or []), gr.Radio(), previous_tool, ""
    question = (
        f"{choice} 시험 일정 알려줘"
        if previous_tool == "certificate"
        else f"{choice}에 대해 더 자세히 알려줘"
    )
    _, updated, selector, routed_tool, status = respond(
        question, history, profile_state, previous_tool
    )
    return updated, selector, routed_tool, status


def reset_chat() -> tuple[str, list[dict[str, str]], gr.Radio, str, str]:
    return (
        "",
        [{"role": "assistant", "content": "새 대화를 시작했어요. 무엇을 준비할까요?"}],
        gr.Radio(choices=[], visible=False),
        "",
        "🤖 질문의 맥락을 읽고 적절한 기능을 자동으로 선택해요.",
    )


def select_feature(tool_key: str) -> tuple:
    spec = TOOL_MAP[tool_key]
    button_updates = [
        gr.update(variant="primary" if tool.key == tool_key else "secondary")
        for tool in TOOLS
    ]
    return (
        tool_key,
        f"{spec.icon} **{spec.label}** 기능을 선택했어요. 편하게 질문해 주세요.",
        *button_updates,
    )


CSS = """
@font-face{
  font-family:"Chiron Go Round TC";
  src:url("/gradio_api/file=assets/fonts/ChironGoRoundTC-VariableFont_wght.ttf") format("truetype");
  font-style:normal;
  font-weight:100 900;
  font-display:swap;
}

:root{
  --glass-blue:#4b93ff;
  --glass-blue-deep:#225bd7;
  --glass-cyan:#bfe9ff;
  --ink:#172033;
  --muted:#687386;
  --glass-border:rgba(255,255,255,.82);
  --glass-fill:rgba(247,250,255,.56);
  --glass-shadow:0 22px 50px rgba(62,77,108,.18),0 6px 14px rgba(49,75,121,.12);
}

html,body{min-height:100%;background:#e7e8ea!important}
body:before,body:after{
  content:"";position:fixed;z-index:0;pointer-events:none;border-radius:50%;filter:blur(3px);
}
body:before{
  width:560px;height:560px;left:-170px;top:-180px;
  background:radial-gradient(circle at 55% 52%,rgba(255,255,255,.72),rgba(195,220,255,.2) 48%,transparent 72%);
}
body:after{
  width:620px;height:620px;right:-210px;bottom:-260px;
  background:radial-gradient(circle at 45% 40%,rgba(255,255,255,.56),rgba(203,211,255,.18) 50%,transparent 72%);
}

.gradio-container{
  position:relative;z-index:1;max-width:none!important;margin:0!important;padding:24px!important;
  min-height:100vh!important;color:var(--ink)!important;
  font-family:"Chiron Go Round TC",sans-serif!important;
  background:
    linear-gradient(rgba(103,112,125,.055) 1px,transparent 1px),
    linear-gradient(90deg,rgba(103,112,125,.055) 1px,transparent 1px),
    linear-gradient(135deg,#dfe1e4 0%,#f1f2f3 48%,#dfe1e5 100%)!important;
  background-size:32px 32px,32px 32px,auto!important;
}
.gradio-container *{font-family:"Chiron Go Round TC",sans-serif!important}

.onboarding{max-width:720px;margin:2vh auto 5vh!important}
.hero{text-align:center;padding:16px 8px 24px}
.hero .eyebrow{
  display:inline-flex;align-items:center;gap:7px;padding:7px 13px;border-radius:999px;
  color:#49627f;font-size:12px;font-weight:700;letter-spacing:.08em;
  border:1px solid rgba(255,255,255,.9);
  background:linear-gradient(145deg,rgba(255,255,255,.72),rgba(222,234,250,.48));
  box-shadow:inset 0 1px 1px #fff,0 7px 16px rgba(65,83,115,.12);
}
.hero .logo{
  display:flex;width:72px;height:72px;margin:18px auto 15px;align-items:center;justify-content:center;
  border-radius:25px;font-size:31px;border:1px solid rgba(255,255,255,.88);
  background:
    radial-gradient(circle at 28% 18%,rgba(255,255,255,.95),transparent 30%),
    linear-gradient(145deg,rgba(194,229,255,.88),rgba(87,145,245,.63));
  box-shadow:inset 0 2px 2px rgba(255,255,255,.95),inset 0 -5px 12px rgba(37,92,192,.2),
    0 12px 22px rgba(57,103,187,.25),0 3px 0 rgba(121,152,205,.36);
}
.hero h1{font-size:34px;letter-spacing:-.045em;margin:0 0 9px;color:#141a25}
.hero p{margin:0;color:var(--muted);line-height:1.7;font-size:15px}

.glass-card,.card,.chat-card{
  position:relative;overflow:hidden;padding:28px!important;border-radius:32px!important;
  border:1px solid var(--glass-border)!important;
  background:
    linear-gradient(145deg,rgba(255,255,255,.52),rgba(224,227,232,.34))!important;
  -webkit-backdrop-filter:blur(28px) saturate(145%);backdrop-filter:blur(28px) saturate(145%);
  box-shadow:inset 0 2px 2px rgba(255,255,255,.96),inset 0 -2px 4px rgba(83,93,108,.2),
    0 1px 0 rgba(126,139,160,.34),0 19px 30px rgba(57,64,76,.18),
    0 0 18px rgba(120,173,255,.09)!important;
}
.glass-card:before,.card:before,.chat-card:before{
  content:"";position:absolute;z-index:0;inset:1px 12px auto;height:42%;pointer-events:none;
  border-radius:29px 29px 55% 55%;
  background:linear-gradient(180deg,rgba(255,255,255,.34),transparent);
}
.glass-card>* ,.card>* ,.chat-card>*{position:relative;z-index:1}
.glass-card>.block,.glass-card>.form,.card>.block,.card>.form{
  border:0!important;background:transparent!important;box-shadow:none!important;
}
.glass-card .styler,.card .styler,.chat-card .styler{
  border:0!important;background:transparent!important;box-shadow:none!important;
}
.card h3{margin:0 0 5px!important;font-size:21px!important;letter-spacing:-.035em}
.form-note{margin:-1px 0 14px;color:var(--muted);font-size:13px}

.gradio-container .form{
  border:0!important;background:transparent!important;box-shadow:none!important;
}
.gradio-container label span{color:#344054!important;font-weight:600!important;font-size:13px!important}
.gradio-container input,.gradio-container textarea{
  min-height:48px!important;border-radius:16px!important;color:var(--ink)!important;
  border:1px solid rgba(144,166,201,.42)!important;
  background:linear-gradient(145deg,rgba(245,249,255,.74),rgba(255,255,255,.42))!important;
  box-shadow:inset 0 2px 4px rgba(68,91,127,.09),inset 0 -1px 1px rgba(255,255,255,.88),
    0 1px 0 rgba(255,255,255,.9)!important;
  -webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px);
}
.gradio-container input::placeholder,.gradio-container textarea::placeholder{color:#8993a3!important}
.gradio-container input:focus,.gradio-container textarea:focus{
  border-color:rgba(72,136,245,.72)!important;
  box-shadow:inset 0 2px 4px rgba(68,91,127,.08),0 0 0 4px rgba(75,147,255,.13),
    0 7px 18px rgba(61,111,199,.12)!important;
}

.primary3d,.secondary3d{
  min-height:49px!important;border-radius:18px!important;font-weight:700!important;
  transition:transform .16s ease,box-shadow .16s ease,filter .16s ease!important;
}
.primary3d{
  color:#fff!important;border:1px solid rgba(255,255,255,.7)!important;
  background:
    radial-gradient(circle at 50% -30%,rgba(255,255,255,.8),transparent 45%),
    linear-gradient(180deg,#73b8ff 0%,#3f8cf4 48%,#2469dc 100%)!important;
  text-shadow:0 1px 1px rgba(19,62,134,.35);
  box-shadow:inset 0 2px 2px rgba(255,255,255,.86),inset 0 -4px 8px rgba(24,73,169,.24),
    0 5px 0 rgba(35,86,174,.42),0 13px 24px rgba(50,111,220,.25)!important;
}
.secondary3d{
  color:#29466f!important;border:1px solid rgba(255,255,255,.82)!important;
  background:linear-gradient(145deg,rgba(255,255,255,.75),rgba(220,232,249,.5))!important;
  box-shadow:inset 0 2px 2px rgba(255,255,255,.94),inset 0 -2px 4px rgba(85,111,153,.13),
    0 4px 0 rgba(129,151,184,.25),0 9px 18px rgba(64,80,109,.13)!important;
}
.primary3d:hover,.secondary3d:hover{filter:brightness(1.035);transform:translateY(-1px)}
.primary3d:active,.secondary3d:active{transform:translateY(3px);box-shadow:inset 0 2px 5px rgba(35,70,125,.18),0 2px 5px rgba(51,75,111,.15)!important}

.chat-shell{max-width:960px;margin:0 auto!important;padding-bottom:30px}
.chat-topbar{
  align-items:center!important;margin:0 0 14px;padding:8px 3px!important;
}
.chat-heading h1{margin:0!important;font-size:28px!important;letter-spacing:-.045em}
.chat-heading p{margin:5px 0 0;color:var(--muted);font-size:14px}
.profile-chip,.route-status{
  border:1px solid rgba(255,255,255,.78)!important;border-radius:18px!important;
  background:linear-gradient(145deg,rgba(255,255,255,.6),rgba(224,235,250,.42))!important;
  -webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px);
  box-shadow:inset 0 1px 1px rgba(255,255,255,.9),0 7px 18px rgba(64,82,113,.09)!important;
}
.profile-chip{padding:10px 15px!important;color:#43516a}
.route-status{padding:9px 15px!important;color:#285d9f}
.profile-chip p,.route-status p{margin:0!important}

.feature-label{margin:14px 2px 7px;color:#657083;font-size:13px}
.feature-menu{gap:10px!important;margin:0 0 15px!important}
.feature-glass{
  min-height:62px!important;border-radius:24px!important;color:#24344e!important;
  border:1px solid rgba(255,255,255,.92)!important;
  background:
    radial-gradient(circle at 22% 4%,rgba(255,255,255,.94),transparent 37%),
    linear-gradient(145deg,rgba(255,255,255,.63),rgba(202,214,231,.34))!important;
  box-shadow:inset 0 2px 2px rgba(255,255,255,.98),inset 0 -3px 5px rgba(86,102,128,.18),
    0 4px 0 rgba(110,124,146,.25),0 10px 17px rgba(57,67,83,.14),
    -2px 0 7px rgba(129,206,255,.18),2px 0 7px rgba(255,190,128,.11)!important;
  transition:transform .16s ease,filter .16s ease!important;
}
.feature-glass:hover{transform:translateY(-2px);filter:brightness(1.04)}
.feature-glass:active{transform:translateY(3px)}
.feature-glass.primary{
  color:#fff!important;
  background:
    radial-gradient(circle at 30% -20%,rgba(255,255,255,.82),transparent 44%),
    linear-gradient(180deg,rgba(113,177,255,.92),rgba(48,111,222,.9))!important;
  text-shadow:0 1px 1px rgba(16,55,122,.35);
  box-shadow:inset 0 2px 2px #fff,inset 0 -4px 7px rgba(27,73,161,.28),
    0 5px 0 rgba(44,85,155,.4),0 12px 20px rgba(49,102,194,.25)!important;
}

.chat-card{padding:15px!important;border-radius:34px!important}
#main-chat{
  border:0!important;border-radius:25px!important;
  background:linear-gradient(145deg,rgba(242,247,254,.5),rgba(255,255,255,.28))!important;
}
#main-chat .message{
  max-width:82%!important;padding:11px 15px!important;border-radius:22px!important;
  border:1px solid rgba(255,255,255,.7)!important;
  box-shadow:inset 0 1px 1px rgba(255,255,255,.48),0 5px 13px rgba(50,70,105,.1)!important;
}
#main-chat .message.user,#main-chat [data-testid="user"] .message{
  color:#fff!important;border-bottom-right-radius:7px!important;
  background:
    radial-gradient(circle at 30% 0,rgba(255,255,255,.35),transparent 45%),
    linear-gradient(145deg,#58a7ff,#317fe9 65%,#2466ce)!important;
}
#main-chat .message.bot,#main-chat [data-testid="bot"] .message{
  color:var(--ink)!important;border-bottom-left-radius:7px!important;
  background:linear-gradient(145deg,rgba(255,255,255,.82),rgba(224,233,246,.68))!important;
}
#main-chat .role:has(.schedule-response){
  width:100%!important;max-width:100%!important;
}
#main-chat .bot.message:has(.schedule-response){
  width:100%!important;max-width:100%!important;
}
#main-chat .message:has(.schedule-response){
  width:100%!important;max-width:100%!important;padding:14px!important;
}
#main-chat .message table{display:none!important}
#main-chat .schedule-response{width:min(100%,560px);margin:0;padding:1px}
#main-chat .schedule-title{margin:0 0 14px;font-size:20px;line-height:1.35;color:#18233a}
#main-chat .schedule-section{margin:12px 0}
#main-chat .schedule-section-title{margin:0 0 8px;font-size:14px;color:#4a5870}
#main-chat .schedule-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
#main-chat .exam-card{
  padding:13px;border:1px solid rgba(255,255,255,.88);border-radius:19px;
  background:linear-gradient(145deg,rgba(255,255,255,.72),rgba(213,224,240,.46));
  box-shadow:inset 0 1px 1px #fff,0 6px 14px rgba(51,65,91,.1);
}
#main-chat .exam-card-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}
#main-chat .exam-round{font-weight:750;color:#1f2b42}
#main-chat .exam-status{
  flex:none;padding:4px 8px;border-radius:999px;font-size:11px;color:#2760a9;
  background:rgba(204,226,255,.72);border:1px solid rgba(255,255,255,.9)
}
#main-chat .exam-status.done{color:#667083;background:rgba(225,228,233,.78)}
#main-chat .exam-info{display:grid;grid-template-columns:64px 1fr;gap:5px 8px;font-size:12px;line-height:1.45}
#main-chat .exam-info span{color:#7b8492}
#main-chat .exam-info strong{color:#303b4e;font-weight:600;overflow-wrap:anywhere}
#main-chat .schedule-meta{
  margin-top:13px;padding:11px 13px;border-radius:15px;font-size:12px;line-height:1.65;color:#5e6879;
  background:rgba(239,243,249,.62);border:1px solid rgba(255,255,255,.76)
}
#main-chat .schedule-meta a{color:#276dd4;text-decoration:none;font-weight:650}
#main-chat .schedule-note{margin:9px 2px 0;color:#7b8491;font-size:11px}
.composer-row{align-items:end!important;gap:10px!important}
.composer-input{flex:1}
.composer-input textarea{border-radius:21px!important}
.send-pill{min-width:112px!important}

footer{display:none!important}
@media(max-width:700px){
  .gradio-container{padding:12px!important;background-size:24px 24px,24px 24px,auto!important}
  .onboarding{margin-top:0!important}.hero{padding-top:8px}.hero h1{font-size:27px}
  .hero .logo{width:62px;height:62px;border-radius:22px}
  .glass-card,.card{padding:20px!important;border-radius:26px!important}
  .chat-topbar{flex-direction:column!important;align-items:flex-start!important}
  .chat-heading h1{font-size:24px!important}.chat-card{padding:9px!important}
  #main-chat .message{max-width:90%!important}
  #main-chat .message:has(.schedule-response){width:100%!important;max-width:100%!important}
  #main-chat .schedule-grid{grid-template-columns:1fr}
  .composer-row{gap:7px!important}.send-pill{min-width:80px!important}
  .feature-menu{display:grid!important;grid-template-columns:1fr 1fr!important}
  .feature-glass{min-width:0!important}
}
"""


with gr.Blocks(title="취업준비 도움 챗봇") as demo:
    profile_state = gr.State({})
    previous_tool = gr.State("")

    with gr.Column(visible=True, elem_classes=["onboarding"]) as profile_page:
        gr.HTML(
            '<section class="hero"><span class="eyebrow">CAREER AI ASSISTANT</span>'
            '<div class="logo">💼</div>'
            "<h1>취업 준비, 한 곳에서 시작해요</h1>"
            "<p>프로필을 입력하면 질문의 맥락에 맞는 기능을<br>"
            "AI가 자동으로 선택해 도와드려요.</p></section>"
        )
        with gr.Group(elem_classes=["card", "glass-card"]):
            gr.Markdown("### 먼저, 나를 알려주세요")
            gr.HTML('<p class="form-note">알고 있는 정보만 편하게 입력해 주세요. 나중에 수정할 수 있어요.</p>')
            education = gr.Textbox(label="학력·전공", placeholder="예: 경영학과, 컴퓨터공학과")
            target_job = gr.Textbox(label="희망 직무", placeholder="선택 입력: 은행 IT, 데이터 분석가")
            skills = gr.Textbox(label="보유 기술", placeholder="쉼표로 구분: Python, SQL")
            experiences = gr.Textbox(label="프로젝트·경험", placeholder="쉼표로 구분해 입력")
            certs = gr.Textbox(label="보유 자격증", placeholder="쉼표로 구분: SQLD, 컴활")
            enter = gr.Button("챗봇 입장하기  →", variant="primary", elem_classes=["primary3d"])
            profile_error = gr.Markdown("")

    with gr.Column(visible=False, elem_classes=["chat-shell"]) as chat_page:
        with gr.Row(elem_classes=["chat-topbar"]):
            back = gr.Button("← 프로필 수정", elem_classes=["secondary3d"], scale=0)
            gr.HTML(
                '<div class="chat-heading"><h1>취업준비 코치</h1>'
                "<p>하고 싶은 말을 편하게 입력하면 알맞은 기능으로 연결할게요 ✨</p></div>"
            )
        profile_summary = gr.Markdown(elem_classes=["profile-chip"])
        route_status = gr.Markdown(
            "🤖 질문의 맥락을 읽고 적절한 기능을 자동으로 선택해요.",
            elem_classes=["route-status"],
        )
        gr.HTML('<p class="feature-label">원하는 기능을 선택하거나 바로 질문해 주세요.</p>')
        with gr.Row(elem_classes=["feature-menu"]):
            feature_buttons = [
                gr.Button(
                    f"{tool.icon} {tool.label}",
                    variant="secondary",
                    elem_classes=["feature-glass"],
                )
                for tool in TOOLS
            ]
        with gr.Group(elem_classes=["chat-card"]):
            chatbot = gr.Chatbot(
                value=[
                    {
                        "role": "assistant",
                        "content": "안녕하세요! 준비하고 싶은 내용을 편하게 말씀해 주세요.",
                    }
                ],
                height=460,
                buttons=["copy", "copy_all"],
                layout="bubble",
                show_label=False,
                elem_id="main-chat",
            )
            with gr.Row(elem_classes=["composer-row"]):
                message = gr.Textbox(
                    label="질문",
                    placeholder="무엇을 준비하고 있나요?",
                    lines=2,
                    elem_classes=["composer-input"],
                )
                send = gr.Button(
                    "보내기",
                    variant="primary",
                    elem_classes=["primary3d", "send-pill"],
                    scale=0,
                )
            with gr.Row():
                clear = gr.Button("새 대화", elem_classes=["secondary3d"])
            follow_up = gr.Radio(
                choices=[],
                label="결과를 선택해 이어서 질문하기",
                visible=False,
                interactive=True,
            )

    enter.click(
        enter_chat,
        inputs=[education, target_job, skills, experiences, certs],
        outputs=[profile_state, profile_page, chat_page, profile_summary, profile_error],
    )
    back.click(
        lambda: (gr.update(visible=True), gr.update(visible=False)),
        outputs=[profile_page, chat_page],
    )
    for button, tool in zip(feature_buttons, TOOLS):
        button.click(
            lambda key=tool.key: select_feature(key),
            outputs=[previous_tool, route_status, *feature_buttons],
        )
    chat_inputs = [message, chatbot, profile_state, previous_tool]
    chat_outputs = [message, chatbot, follow_up, previous_tool, route_status]
    send.click(respond, inputs=chat_inputs, outputs=chat_outputs)
    message.submit(respond, inputs=chat_inputs, outputs=chat_outputs)
    follow_up.input(
        choose_follow_up,
        inputs=[follow_up, chatbot, profile_state, previous_tool],
        outputs=[chatbot, follow_up, previous_tool, route_status],
    )
    clear.click(
        reset_chat,
        outputs=[message, chatbot, follow_up, previous_tool, route_status],
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7860"))
    demo.queue(default_concurrency_limit=8).launch(
        server_name="0.0.0.0",
        server_port=port,
        show_error=False,
        css=CSS,
    )
