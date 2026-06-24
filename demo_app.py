from __future__ import annotations

import os
from dataclasses import dataclass, field
from uuid import uuid4

import gradio as gr
from dotenv import load_dotenv

from tools.spec_recommend import NAME, _recent_recommendation_names, run

load_dotenv()


@dataclass
class DemoProfile:
    session_id: str = ""
    education: str = ""
    target_job: str = ""
    skills: list[str] = field(default_factory=list)
    experiences: list[str] = field(default_factory=list)
    certs: list[str] = field(default_factory=list)


def _split_tags(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _build_profile(
    profile_state: dict[str, object],
) -> DemoProfile:
    return DemoProfile(
        session_id=str(profile_state.get("session_id", "")),
        education=str(profile_state.get("education", "")),
        target_job=str(profile_state.get("target_job", "")),
        skills=list(profile_state.get("skills", [])),
        experiences=list(profile_state.get("experiences", [])),
        certs=list(profile_state.get("certs", [])),
    )


def apply_profile(
    profile_state: dict[str, object],
    education: str,
    target_job: str,
    skills: str,
    experiences: str,
    certs: str,
) -> tuple[dict[str, object], str]:
    updated = {
        "session_id": profile_state.get("session_id") or str(uuid4()),
        "education": (education or "").strip(),
        "target_job": (target_job or "").strip(),
        "skills": _split_tags(skills),
        "experiences": _split_tags(experiences),
        "certs": _split_tags(certs),
    }
    summary = [
        f"**희망 직무:** {updated['target_job'] or '미입력'}",
        f"**보유 기술:** {', '.join(updated['skills']) or '미입력'}",
        f"**보유 자격증:** {', '.join(updated['certs']) or '미입력'}",
    ]
    return updated, "✅ 프로필이 채팅에 적용됐어요.  \n" + " · ".join(summary)


def respond(
    message: str,
    history: list[dict[str, str]] | None,
    profile_state: dict[str, object],
) -> tuple[str, list[dict[str, str]], gr.Radio]:
    history = list(history or [])
    message = (message or "").strip()
    if not message:
        return "", history, gr.Radio()

    profile = _build_profile(profile_state)
    answer = run(profile, message)
    recommendations = _recent_recommendation_names(profile)
    history.extend(
        [
            {"role": "user", "content": message},
            {"role": "assistant", "content": answer},
        ]
    )
    selector = gr.Radio(
        choices=recommendations,
        value=None,
        visible=bool(recommendations),
        label="추천 자격증을 클릭하면 시험 일정을 보여드려요",
        interactive=True,
    )
    return "", history, selector


def show_selected_schedule(
    selected_certificate: str | None,
    history: list[dict[str, str]] | None,
    profile_state: dict[str, object],
) -> tuple[list[dict[str, str]], gr.Radio]:
    history = list(history or [])
    if not selected_certificate:
        return history, gr.Radio()
    profile = _build_profile(profile_state)
    question = f"{selected_certificate} 시험 일정 알려줘"
    answer = run(profile, question)
    history.extend(
        [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
    )
    return history, gr.Radio(value=None)


def use_example(prompt: str) -> str:
    return prompt


CSS = """
:root {
  --primary: #2563eb;
  --primary-dark: #1e40af;
  --surface: #ffffff;
  --background: #f8fafc;
  --text: #0f172a;
  --sub-text: #64748b;
  --border: #e2e8f0;
}

.gradio-container {
  max-width: 1120px !important;
  margin: 0 auto !important;
  background: var(--background);
  color: var(--text);
}

.hero {
  padding: 22px 24px;
  border: 1px solid var(--border);
  border-radius: 18px;
  background: linear-gradient(135deg, #eff6ff 0%, #ffffff 70%);
  margin-bottom: 14px;
}

.hero h1 { margin: 0 0 8px; font-size: 28px; }
.hero p { margin: 0; color: var(--sub-text); }
.profile-panel, .quick-panel {
  border: 1px solid var(--border) !important;
  border-radius: 14px !important;
  background: var(--surface) !important;
}

footer { display: none !important; }
"""


with gr.Blocks(title=f"취업준비 챗봇 · {NAME}") as demo:
    profile_state = gr.State(
        {
            "session_id": str(uuid4()),
            "education": "",
            "target_job": "",
            "skills": [],
            "experiences": [],
            "certs": [],
        }
    )
    gr.HTML(
        """
        <section class="hero">
          <h1>🎯 취업준비 챗봇 — 자격증 추천</h1>
          <p>희망 직무에 맞는 금융·데이터·IT 자격증을 추천하고
          올해 시험 일정을 공식 출처 기준으로 안내해 드려요.</p>
        </section>
        """
    )

    with gr.Row():
        with gr.Column(scale=1, min_width=280, elem_classes=["profile-panel"]):
            gr.Markdown("### 내 프로필")
            education = gr.Textbox(
                label="학력·전공",
                placeholder="예: 경영학과, 컴퓨터공학과",
            )
            target_job = gr.Textbox(
                label="희망 직무",
                placeholder="예: 데이터 분석가, 은행 IT",
            )
            skills = gr.Textbox(
                label="보유 기술",
                placeholder="쉼표로 구분: Python, SQL",
            )
            experiences = gr.Textbox(
                label="프로젝트·경험",
                placeholder="쉼표로 구분해 입력",
            )
            certs = gr.Textbox(
                label="보유 자격증",
                placeholder="쉼표로 구분: SQLD, 컴활",
            )
            apply_profile_button = gr.Button(
                "프로필 적용",
                variant="primary",
            )
            profile_status = gr.Markdown(
                "⚪ 아직 프로필이 적용되지 않았어요. 입력 후 **프로필 적용**을 눌러주세요."
            )

        with gr.Column(scale=2, min_width=420):
            chatbot = gr.Chatbot(
                value=[
                    {
                        "role": "assistant",
                        "content": (
                            "안녕하세요! 희망 직무를 알려주시면 자격증을 추천해 드릴게요. "
                            "자격증명을 입력하면 올해 일정도 확인할 수 있어요."
                        ),
                    }
                ],
                height=540,
                buttons=["copy", "copy_all"],
                label="자격증 추천 상담",
            )
            message = gr.Textbox(
                label="질문",
                placeholder="예: 데이터 분석가 자격증 추천해줘",
                lines=2,
            )
            with gr.Row():
                submit = gr.Button("보내기", variant="primary")
                clear = gr.Button("새 대화")
            recommendation_selector = gr.Radio(
                choices=[],
                label="추천 자격증을 클릭하면 시험 일정을 보여드려요",
                visible=False,
                interactive=True,
            )

    with gr.Group(elem_classes=["quick-panel"]):
        gr.Markdown("### 빠른 질문")
        with gr.Row():
            examples = [
                ("데이터 분석 자격증", "데이터 분석가에게 필요한 자격증 추천해줘"),
                ("은행 취업 자격증", "은행 취업에 도움이 되는 자격증 추천해줘"),
                ("SQLD 시험 일정", "SQLD 올해 시험 일정 알려줘"),
                ("투운사 시험 일정", "투운사 시험 일정 알려줘"),
            ]
            for label, prompt in examples:
                button = gr.Button(label, size="sm")
                button.click(
                    fn=lambda value=prompt: use_example(value),
                    outputs=message,
                )

    gr.Markdown(
        """
        **안내:** 시험 일정은 저장된 공식 자료를 기준으로 제공됩니다.
        일정은 변경될 수 있으므로 접수 전 반드시 시행기관 공식 사이트에서 확인해 주세요.
        """
    )

    apply_profile_button.click(
        apply_profile,
        inputs=[
            profile_state,
            education,
            target_job,
            skills,
            experiences,
            certs,
        ],
        outputs=[profile_state, profile_status],
    )

    inputs = [message, chatbot, profile_state]
    outputs = [message, chatbot, recommendation_selector]
    submit.click(respond, inputs=inputs, outputs=outputs)
    message.submit(respond, inputs=inputs, outputs=outputs)
    recommendation_selector.input(
        show_selected_schedule,
        inputs=[recommendation_selector, chatbot, profile_state],
        outputs=[chatbot, recommendation_selector],
    )
    clear.click(
        lambda: (
            "",
            [
                {
                    "role": "assistant",
                    "content": "새 대화를 시작했어요. 어떤 직무를 준비하고 있나요?",
                }
            ],
            {
                "session_id": str(uuid4()),
                "education": "",
                "target_job": "",
                "skills": [],
                "experiences": [],
                "certs": [],
            },
            "⚪ 새 대화를 시작했어요. 프로필을 다시 적용해 주세요.",
            gr.Radio(choices=[], value=None, visible=False),
        ),
        outputs=[
            message,
            chatbot,
            profile_state,
            profile_status,
            recommendation_selector,
        ],
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7860"))
    demo.queue(default_concurrency_limit=8).launch(
        server_name="0.0.0.0",
        server_port=port,
        show_error=False,
        css=CSS,
    )
