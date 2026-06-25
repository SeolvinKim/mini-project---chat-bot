from __future__ import annotations

import importlib
import os
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import gradio as gr
from dotenv import load_dotenv

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
    description: str
    examples: tuple[str, ...]


TOOLS = (
    ToolSpec(
        "job",
        "tools.recommend_job",
        "직무 추천",
        "🧭",
        "내 경험과 역량에 맞는 금융권 직무를 찾아요.",
        ("금융 데이터 직무를 추천해줘", "고객 상담을 좋아하는데 어떤 직무가 맞을까?"),
    ),
    ToolSpec(
        "cover_letter",
        "tools.cover_letter",
        "자소서 피드백",
        "✍️",
        "자소서의 구체성·직무 연관성·가독성을 점검해요.",
        ("은행 디지털 직무 지원동기를 봐줘", "이 자소서를 STAR 구조로 피드백해줘"),
    ),
    ToolSpec(
        "interview",
        "tools.interview",
        "면접 질문",
        "🎤",
        "직무와 프로젝트를 바탕으로 예상 질문을 만들어요.",
        ("데이터 분석 직무 면접 질문을 만들어줘", "프로젝트 기반 압박 질문을 내줘"),
    ),
    ToolSpec(
        "certificate",
        "tools.spec_recommend",
        "자격증 추천",
        "🏅",
        "직무에 맞는 자격증과 올해 시험 일정을 안내해요.",
        ("데이터 분석 자격증을 추천해줘", "SQLD 올해 시험 일정 알려줘"),
    ),
)
TOOL_MAP = {tool.key: tool for tool in TOOLS}
DEFAULT_TOOL = TOOLS[0].key


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


def select_tool(tool_key: str) -> tuple:
    spec = TOOL_MAP[tool_key]
    label = f"{spec.icon} **{spec.label}** · {spec.description}"
    button_updates = [
        gr.update(variant="primary" if tool.key == tool_key else "secondary")
        for tool in TOOLS
    ]
    return (
        tool_key,
        label,
        gr.Radio(choices=list(spec.examples), value=None),
        "",
        *button_updates,
    )


def _extract_choices(answer: str) -> list[str]:
    choices = []
    for line in answer.splitlines():
        match = re.match(r"^#{0,3}\s*\d+\.\s*(.+?)\s*$", line.strip())
        if match:
            choices.append(re.sub(r"[*_`]", "", match.group(1)).strip())
    return choices[:5]


def respond(
    message: str,
    history: list[dict[str, str]] | None,
    profile_state: dict[str, object],
    active_tool: str,
) -> tuple[str, list[dict[str, str]], gr.Radio]:
    history = list(history or [])
    message = (message or "").strip()
    if not message:
        return "", history, gr.Radio()

    spec = TOOL_MAP[active_tool]
    run = _load_run(spec)
    if run is None:
        answer = (
            f"아직 **{spec.label}** 코드가 이 브랜치에 병합되지 않았어요. "
            "담당 Tool 브랜치를 병합하면 자동으로 활성화됩니다."
        )
    else:
        try:
            answer = str(run(_profile_from_state(profile_state), message))
        except Exception:
            answer = "요청을 처리하지 못했어요. 입력을 확인하고 다시 시도해 주세요."

    history.extend(
        [{"role": "user", "content": message}, {"role": "assistant", "content": answer}]
    )
    choices = _extract_choices(answer)
    return "", history, gr.Radio(choices=choices, value=None, visible=bool(choices))


def choose_follow_up(
    choice: str | None,
    history: list[dict[str, str]] | None,
    profile_state: dict[str, object],
    active_tool: str,
) -> tuple[list[dict[str, str]], gr.Radio]:
    if not choice:
        return list(history or []), gr.Radio()
    if active_tool == "certificate":
        question = f"{choice} 시험 일정 알려줘"
    else:
        question = f"{choice}에 대해 더 자세히 알려줘"
    _, updated, selector = respond(question, history, profile_state, active_tool)
    return updated, selector


def reset_chat() -> tuple[str, list[dict[str, str]], gr.Radio]:
    return "", [{"role": "assistant", "content": "새 대화를 시작했어요. 무엇을 준비할까요?"}], gr.Radio(choices=[], visible=False)


CSS = """
@import url('https://fonts.googleapis.com/css2?family=Gowun+Dodum&display=swap');
:root{--blue:#3182f6;--blue-dark:#1b64da;--soft:#e8f3ff;--bg:#f4f7fb;--text:#191f28;--sub:#6b7684;--line:#e5e8eb}
.gradio-container{max-width:1100px!important;margin:auto!important;padding:24px!important;min-height:100vh;background:var(--bg);font-family:"Gowun Dodum","Noto Sans KR",sans-serif!important;color:var(--text)}
.onboarding{max-width:760px;margin:4vh auto 0}.hero{text-align:center;padding:18px 8px 24px}.hero .logo{display:inline-flex;width:60px;height:60px;align-items:center;justify-content:center;border-radius:20px;background:linear-gradient(145deg,#55a3ff,#1671e8);box-shadow:0 12px 24px rgba(49,130,246,.28);font-size:28px}.hero h1{font-size:32px;margin:16px 0 6px;font-weight:700;letter-spacing:-.02em}.hero p{color:var(--sub);line-height:1.65}
.card{padding:28px!important;border:1px solid #fff!important;border-radius:28px!important;background:#fff!important;box-shadow:0 12px 30px rgba(49,130,246,.12)!important}
input,textarea{border-radius:16px!important;background:#f9fafb!important;border:1px solid var(--line)!important}input:focus,textarea:focus{border-color:var(--blue)!important;box-shadow:0 0 0 4px rgba(49,130,246,.1)!important}
.primary3d,.secondary3d{border:0!important;border-radius:16px!important;font-weight:700!important;min-height:48px!important;box-shadow:none!important;transition:background .15s ease!important}
.primary3d{color:#fff!important;background:var(--blue)!important}.primary3d:hover{background:var(--blue-dark)!important}
.secondary3d{color:var(--blue-dark)!important;background:var(--soft)!important}.secondary3d:hover{background:#d8eafe!important}
.chat-shell{max-width:900px;margin:auto}
.tool-menu button{border-radius:16px!important;min-height:64px!important;font-weight:600!important;border:1px solid var(--line)!important;background:#fff!important;box-shadow:none!important;color:var(--text)!important;transition:border-color .15s,background .15s!important}
.tool-menu button:hover{border-color:var(--blue)!important;background:var(--soft)!important}
.tool-menu button.primary{background:var(--blue)!important;border-color:var(--blue)!important;color:#fff!important}
.profile-chip,.active-tool{padding:10px 14px;border-radius:14px;background:var(--soft);color:var(--blue-dark)}
.chat-card{padding:14px!important;border-radius:28px!important;background:#fff!important;border:1px solid #fff!important;box-shadow:0 12px 30px rgba(49,130,246,.12)!important}
#main-chat .message{border:0!important;border-radius:22px!important;padding:11px 15px!important;max-width:80%!important}#main-chat .message.user,#main-chat [data-testid="user"] .message{background:#0b84ff!important;color:#fff!important;border-bottom-right-radius:7px!important}#main-chat .message.bot,#main-chat [data-testid="bot"] .message{background:#edf0f3!important;color:var(--text)!important;border-bottom-left-radius:7px!important}
footer{display:none!important}@media(max-width:700px){.gradio-container{padding:12px!important}.card{padding:20px!important}.hero h1{font-size:27px}.tool-menu{flex-direction:column!important}}
"""


with gr.Blocks(title="취업준비 도움 챗봇") as demo:
    profile_state = gr.State({})
    active_tool = gr.State(DEFAULT_TOOL)

    with gr.Column(visible=True, elem_classes=["onboarding"]) as profile_page:
        gr.HTML(
            '<section class="hero"><div class="logo">💼</div>'
            "<h1>취업 준비, 한 곳에서 시작해요</h1>"
            "<p>프로필을 입력하면 직무·자소서·면접·자격증 준비를<br>"
            "하나의 챗봇에서 이어서 도와드려요.</p></section>"
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
            gr.Markdown("# 취업준비 코치\n원하는 기능을 고르고 편하게 질문해 주세요 ✨")
        profile_summary = gr.Markdown(elem_classes=["profile-chip"])
        with gr.Row(elem_classes=["tool-menu"]):
            tool_buttons = []
            for index, spec in enumerate(TOOLS):
                tool_buttons.append(
                    gr.Button(
                        f"{spec.icon} {spec.label}",
                        variant="primary" if index == 0 else "secondary",
                    )
                )
        active_label = gr.Markdown(
            f"{TOOLS[0].icon} **{TOOLS[0].label}** · {TOOLS[0].description}",
            elem_classes=["active-tool"],
        )
        quick_examples = gr.Radio(choices=list(TOOLS[0].examples), label="빠른 질문", interactive=True)
        with gr.Group(elem_classes=["chat-card"]):
            chatbot = gr.Chatbot(
                value=[{"role": "assistant", "content": "안녕하세요! 먼저 원하는 기능을 선택해 주세요."}],
                height=500,
                buttons=["copy", "copy_all"],
                layout="bubble",
                elem_id="main-chat",
            )
            message = gr.Textbox(label="질문", placeholder="무엇을 준비하고 있나요?", lines=2)
            with gr.Row():
                send = gr.Button("보내기", variant="primary", elem_classes=["primary3d"])
                clear = gr.Button("새 대화", elem_classes=["secondary3d"])
            follow_up = gr.Radio(choices=[], label="결과를 선택해 이어서 질문하기", visible=False, interactive=True)

    enter.click(
        enter_chat,
        inputs=[education, target_job, skills, experiences, certs],
        outputs=[profile_state, profile_page, chat_page, profile_summary, profile_error],
    )
    back.click(lambda: (gr.update(visible=True), gr.update(visible=False)), outputs=[profile_page, chat_page])
    for button, spec in zip(tool_buttons, TOOLS):
        button.click(
            lambda key=spec.key: select_tool(key),
            outputs=[active_tool, active_label, quick_examples, message, *tool_buttons],
        )
    quick_examples.input(lambda value: value or "", inputs=quick_examples, outputs=message)
    chat_inputs = [message, chatbot, profile_state, active_tool]
    send.click(respond, inputs=chat_inputs, outputs=[message, chatbot, follow_up])
    message.submit(respond, inputs=chat_inputs, outputs=[message, chatbot, follow_up])
    follow_up.input(
        choose_follow_up,
        inputs=[follow_up, chatbot, profile_state, active_tool],
        outputs=[chatbot, follow_up],
    )
    clear.click(reset_chat, outputs=[message, chatbot, follow_up])


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7860"))
    demo.queue(default_concurrency_limit=8).launch(
        server_name="0.0.0.0",
        server_port=port,
        show_error=False,
        css=CSS,
    )
