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
    if previous_tool in TOOL_MAP and any(
        word in normalized
        for word in ("그거", "그것", "아까", "더", "다른", "자세히", "이어서")
    ):
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

    # 키워드로 명확히 분류되면 LLM 라우팅(round-trip)을 건너뛴다.
    # 모호한 질문(general)일 때만 라우터 LLM이 문맥까지 보고 분류·재작성한다.
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


CSS = """
@import url('https://fonts.googleapis.com/css2?family=Gowun+Dodum&display=swap');
:root{--blue:#3182f6;--blue-dark:#1b64da;--soft:#e8f3ff;--bg:#f4f7fb;--text:#191f28;--sub:#6b7684;--line:#e5e8eb}
.gradio-container{max-width:1100px!important;margin:auto!important;padding:24px!important;min-height:100vh;background:var(--bg);font-family:"Gowun Dodum","Noto Sans KR",sans-serif!important;color:var(--text)}
.onboarding{max-width:760px;margin:4vh auto 0}.hero{text-align:center;padding:18px 8px 24px}.hero .logo{display:inline-flex;width:60px;height:60px;align-items:center;justify-content:center;border-radius:20px;background:linear-gradient(145deg,#55a3ff,#1671e8);box-shadow:0 12px 24px rgba(49,130,246,.28);font-size:28px}.hero h1{font-size:32px;margin:16px 0 6px}.hero p{color:var(--sub);line-height:1.65}
.card{padding:28px!important;border:1px solid #fff!important;border-radius:28px!important;background:#fff!important;box-shadow:0 12px 30px rgba(49,130,246,.12)!important}
input,textarea{border-radius:16px!important;background:#f9fafb!important;border:1px solid var(--line)!important}input:focus,textarea:focus{border-color:var(--blue)!important;box-shadow:0 0 0 4px rgba(49,130,246,.1)!important}
.primary3d,.secondary3d{border:0!important;border-radius:16px!important;font-weight:700!important;min-height:46px!important}.primary3d{color:#fff!important;background:linear-gradient(#4593fa,#2378eb)!important;box-shadow:0 6px 0 #155dc1,0 11px 20px rgba(49,130,246,.2)!important}.secondary3d{color:var(--blue-dark)!important;background:linear-gradient(#fff,#edf5ff)!important;box-shadow:0 4px 0 #c5dcf8!important}
.chat-shell{max-width:900px;margin:auto}.profile-chip,.route-status{padding:10px 14px;border-radius:14px;background:var(--soft);color:var(--blue-dark)}
.chat-card{padding:14px!important;border-radius:28px!important;background:#fff!important;border:1px solid #fff!important;box-shadow:0 12px 30px rgba(49,130,246,.12)!important}
#main-chat .message{border:0!important;border-radius:22px!important;padding:11px 15px!important;max-width:80%!important}#main-chat .message.user,#main-chat [data-testid="user"] .message{background:#0b84ff!important;color:#fff!important;border-bottom-right-radius:7px!important}#main-chat .message.bot,#main-chat [data-testid="bot"] .message{background:#edf0f3!important;color:var(--text)!important;border-bottom-left-radius:7px!important}
footer{display:none!important}@media(max-width:700px){.gradio-container{padding:12px!important}.card{padding:20px!important}.hero h1{font-size:27px}}
"""


with gr.Blocks(title="취업준비 도움 챗봇") as demo:
    profile_state = gr.State({})
    previous_tool = gr.State("")

    with gr.Column(visible=True, elem_classes=["onboarding"]) as profile_page:
        gr.HTML(
            '<section class="hero"><div class="logo">💼</div>'
            "<h1>취업 준비, 한 곳에서 시작해요</h1>"
            "<p>프로필을 입력하면 질문의 맥락에 맞는 기능을<br>"
            "AI가 자동으로 선택해 도와드려요.</p></section>"
        )
        with gr.Group(elem_classes=["card"]):
            gr.Markdown("### 먼저, 나를 알려주세요")
            education = gr.Textbox(label="학력·전공", placeholder="예: 경영학과, 컴퓨터공학과")
            target_job = gr.Textbox(label="희망 직무", placeholder="선택 입력: 은행 IT, 데이터 분석가")
            skills = gr.Textbox(label="보유 기술", placeholder="쉼표로 구분: Python, SQL")
            experiences = gr.Textbox(label="프로젝트·경험", placeholder="쉼표로 구분해 입력")
            certs = gr.Textbox(label="보유 자격증", placeholder="쉼표로 구분: SQLD, 컴활")
            enter = gr.Button("챗봇 입장하기  →", variant="primary", elem_classes=["primary3d"])
            profile_error = gr.Markdown("")

    with gr.Column(visible=False, elem_classes=["chat-shell"]) as chat_page:
        with gr.Row():
            back = gr.Button("← 프로필 수정", elem_classes=["secondary3d"], scale=0)
            gr.Markdown("# 취업준비 코치\n하고 싶은 말을 편하게 입력하면 알맞은 기능으로 연결할게요 ✨")
        profile_summary = gr.Markdown(elem_classes=["profile-chip"])
        route_status = gr.Markdown(
            "🤖 질문의 맥락을 읽고 적절한 기능을 자동으로 선택해요.",
            elem_classes=["route-status"],
        )
        quick_examples = gr.Radio(
            choices=[
                "내 경험에 맞는 금융권 직무를 추천해줘",
                "이 자소서 지원동기를 피드백해줘",
                "데이터 분석 직무 면접 질문을 만들어줘",
                "SQLD 올해 시험 일정 알려줘",
            ],
            label="이렇게 물어보세요",
            interactive=True,
        )
        with gr.Group(elem_classes=["chat-card"]):
            chatbot = gr.Chatbot(
                value=[
                    {
                        "role": "assistant",
                        "content": "안녕하세요! 준비하고 싶은 내용을 편하게 말씀해 주세요.",
                    }
                ],
                height=500,
                buttons=["copy", "copy_all"],
                layout="bubble",
                elem_id="main-chat",
            )
            message = gr.Textbox(label="질문", placeholder="무엇을 준비하고 있나요?", lines=2)
            with gr.Row():
                send = gr.Button("보내기", variant="primary", elem_classes=["primary3d"])
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
    quick_examples.input(lambda value: value or "", inputs=quick_examples, outputs=message)
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
