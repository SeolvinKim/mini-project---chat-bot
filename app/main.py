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
@import url('https://fonts.googleapis.com/css2?family=Gowun+Dodum&family=Noto+Sans+KR:wght@400;500;600;700&display=swap');

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

html,body{min-height:100%;background:#edf1f6!important}
body:before,body:after{
  content:"";position:fixed;z-index:0;pointer-events:none;border-radius:50%;filter:blur(3px);
}
body:before{
  width:560px;height:560px;left:-170px;top:-180px;
  background:radial-gradient(circle at 55% 52%,rgba(178,220,255,.65),rgba(213,231,255,.24) 48%,transparent 72%);
}
body:after{
  width:620px;height:620px;right:-210px;bottom:-260px;
  background:radial-gradient(circle at 45% 40%,rgba(177,197,255,.55),rgba(225,232,255,.2) 50%,transparent 72%);
}

.gradio-container{
  position:relative;z-index:1;max-width:none!important;margin:0!important;padding:24px!important;
  min-height:100vh!important;color:var(--ink)!important;
  font-family:"Noto Sans KR","Gowun Dodum",sans-serif!important;
  background:
    linear-gradient(rgba(255,255,255,.16) 1px,transparent 1px),
    linear-gradient(90deg,rgba(255,255,255,.16) 1px,transparent 1px),
    linear-gradient(135deg,#e8edf3 0%,#f8fafc 48%,#e9edf4 100%)!important;
  background-size:32px 32px,32px 32px,auto!important;
}

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
    linear-gradient(145deg,rgba(255,255,255,.68),rgba(235,241,250,.42))!important;
  -webkit-backdrop-filter:blur(28px) saturate(145%);backdrop-filter:blur(28px) saturate(145%);
  box-shadow:inset 0 1.5px 1px rgba(255,255,255,.95),inset 0 -1px 2px rgba(99,125,166,.18),
    var(--glass-shadow)!important;
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

.tool-menu button{
  border-radius:18px!important;min-height:60px!important;font-weight:700!important;
  border:1px solid rgba(255,255,255,.78)!important;
  background:linear-gradient(145deg,rgba(255,255,255,.6),rgba(224,235,250,.42))!important;
  -webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px);
  box-shadow:inset 0 1px 1px rgba(255,255,255,.9),0 7px 18px rgba(64,82,113,.09)!important;
  color:var(--ink)!important;
  transition:transform .16s ease,box-shadow .16s ease,filter .16s ease!important;
}
.tool-menu button:hover{filter:brightness(1.035);transform:translateY(-1px)}
.tool-menu button.primary{
  color:#fff!important;border:1px solid rgba(255,255,255,.7)!important;
  background:
    radial-gradient(circle at 50% -30%,rgba(255,255,255,.8),transparent 45%),
    linear-gradient(180deg,#73b8ff 0%,#3f8cf4 48%,#2469dc 100%)!important;
  box-shadow:inset 0 2px 2px rgba(255,255,255,.86),inset 0 -4px 8px rgba(24,73,169,.24),
    0 5px 0 rgba(35,86,174,.42),0 13px 24px rgba(50,111,220,.25)!important;
}

.chat-shell{max-width:960px;margin:0 auto!important;padding-bottom:30px}
.chat-topbar{
  align-items:center!important;margin:0 0 14px;padding:8px 3px!important;
}
.chat-heading h1{margin:0!important;font-size:28px!important;letter-spacing:-.045em}
.chat-heading p{margin:5px 0 0;color:var(--muted);font-size:14px}
.profile-chip,.active-tool{
  border:1px solid rgba(255,255,255,.78)!important;border-radius:18px!important;
  background:linear-gradient(145deg,rgba(255,255,255,.6),rgba(224,235,250,.42))!important;
  -webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px);
  box-shadow:inset 0 1px 1px rgba(255,255,255,.9),0 7px 18px rgba(64,82,113,.09)!important;
}
.profile-chip{padding:10px 15px!important;color:#43516a}
.active-tool{padding:9px 15px!important;color:#285d9f}
.profile-chip p,.active-tool p{margin:0!important}

.quick-glass{
  padding:10px 13px 12px!important;margin:3px 0 14px!important;border-radius:22px!important;
  border:1px solid rgba(255,255,255,.78)!important;
  background:rgba(244,248,253,.46)!important;
  box-shadow:inset 0 1px 1px #fff,0 8px 18px rgba(64,82,113,.08)!important;
}
.quick-glass>label>span{padding-left:3px}
.quick-glass .wrap{gap:7px!important}
.quick-glass label:has(input){
  flex:0 1 auto!important;width:auto!important;
  border:1px solid rgba(255,255,255,.82)!important;border-radius:999px!important;
  background:linear-gradient(145deg,rgba(255,255,255,.66),rgba(220,233,251,.46))!important;
  box-shadow:inset 0 1px 1px #fff,0 4px 9px rgba(55,77,111,.1)!important;
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
  .composer-row{gap:7px!important}.send-pill{min-width:80px!important}
  .tool-menu{flex-direction:column!important}
}
"""


with gr.Blocks(title="취업준비 도움 챗봇") as demo:
    profile_state = gr.State({})
    active_tool = gr.State(DEFAULT_TOOL)

    with gr.Column(visible=True, elem_classes=["onboarding"]) as profile_page:
        gr.HTML(
            '<section class="hero"><span class="eyebrow">CAREER AI ASSISTANT</span>'
            '<div class="logo">💼</div>'
            "<h1>취업 준비, 한 곳에서 시작해요</h1>"
            "<p>프로필을 입력하면 직무·자소서·면접·자격증 준비를<br>"
            "하나의 챗봇에서 이어서 도와드려요.</p></section>"
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
                "<p>원하는 기능을 고르고 편하게 질문해 주세요 ✨</p></div>"
            )
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
        quick_examples = gr.Radio(
            choices=list(TOOLS[0].examples),
            label="빠른 질문",
            interactive=True,
            elem_classes=["quick-glass"],
        )
        with gr.Group(elem_classes=["chat-card"]):
            chatbot = gr.Chatbot(
                value=[{"role": "assistant", "content": "안녕하세요! 먼저 원하는 기능을 선택해 주세요."}],
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
