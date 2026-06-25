from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import gradio as gr
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv()

FONT_PATH = ROOT / "assets" / "fonts" / "ChironGoRoundTC-VariableFont_wght.ttf"
if FONT_PATH.exists():
    try:
        gr.set_static_paths(paths=[FONT_PATH])
    except TypeError:
        gr.set_static_paths([FONT_PATH])

APP_TITLE = "AI 면접 질문 생성툴"
PRACTICE_TOTAL = 5
REAL_TOTAL = 10

QUESTION_TYPES = [
    "자기소개",
    "지원동기",
    "직무 역량",
    "프로젝트 경험",
    "협업 경험",
    "문제 해결",
    "기업 및 직무 적합성",
    "상황 대처",
    "꼬리 질문",
    "마무리 질문",
]


@dataclass
class InterviewItem:
    question: str
    question_type: str
    difficulty: str
    intent: str = ""
    evaluation_points: str = ""
    answer_guide: str = ""
    answer: str = ""
    feedback: dict[str, str | int] = field(default_factory=dict)


def empty_session() -> dict:
    return {
        "active": False,
        "session_id": "",
        "mode": "",
        "difficulty": "",
        "profile": {},
        "started_at": "",
        "ended_at": "",
        "total_questions": 0,
        "current_index": 0,
        "items": [],
    }


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _profile_text(profile: dict) -> str:
    skills = ", ".join(profile.get("skills", [])) or "미입력"
    experiences = profile.get("experiences") or "미입력"
    return "\n".join(
        [
            f"학력/전공: {profile.get('education') or '미입력'}",
            f"지원 직무: {profile.get('target_job') or '미입력'}",
            f"보유 기술: {skills}",
            f"보유 자격증: {', '.join(profile.get('certs', [])) or '없음'}",
            f"프로젝트/경험: {experiences}",
            f"추가 메모: {profile.get('memo') or '없음'}",
        ]
    )


def validate_profile(profile: dict) -> tuple[bool, str]:
    target_job = (profile.get("target_job") or "").strip()
    experiences = (profile.get("experiences") or "").strip()
    skills = profile.get("skills", [])
    memo = (profile.get("memo") or "").strip()

    if not target_job:
        return False, "지원 직무를 입력해 주세요. 예: 데이터 분석, 백엔드 개발, 금융 IT"
    if len(experiences) + len(memo) < 20 and not skills:
        return False, "질문 생성을 위해 프로젝트, 경험, 기술 중 하나 이상을 조금 더 구체적으로 입력해 주세요."
    return True, ""


def extract_json(text: str) -> dict:
    cleaned = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


def _history_for_prompt(session: dict) -> list[dict[str, str]]:
    history = []
    for index, item in enumerate(session.get("items", []), start=1):
        history.append(
            {
                "number": str(index),
                "question": item.get("question", ""),
                "answer": item.get("answer", ""),
            }
        )
    return history


def _question_type(session: dict) -> str:
    index = int(session.get("current_index", 0))
    if session.get("mode") == "실전 모드":
        return QUESTION_TYPES[min(index, len(QUESTION_TYPES) - 1)]
    return "지원 정보 맞춤형 질문"


def _call_generation_llm(prompt: str) -> dict:
    from core.llm import get_generation_llm

    response = get_generation_llm().invoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)
    return extract_json(content)


def build_question_prompt(session: dict) -> str:
    current_number = session["current_index"] + 1
    return f"""
당신은 실제 채용 면접관입니다.
지원자의 정보를 바탕으로 지금 물어볼 면접 질문 1개만 생성하세요.

[면접 모드]
{session["mode"]}

[질문 번호]
{current_number} / {session["total_questions"]}

[난이도]
{session["difficulty"]}

[이번 질문 유형]
{_question_type(session)}

[지원자 정보]
{_profile_text(session["profile"])}

[이미 진행한 질문과 답변]
{json.dumps(_history_for_prompt(session), ensure_ascii=False)}

[작성 규칙]
1. 앞선 질문과 중복되지 않게 작성하세요.
2. 질문, 의도, 평가 포인트, 답변 가이드를 분리하세요.
3. 실전 모드는 조금 더 압박감 있게, 연습 모드는 학습자가 답변하기 좋게 작성하세요.
4. 반드시 아래 JSON 형식만 반환하세요.

{{
  "question": "면접 질문 1개",
  "question_type": "질문 유형",
  "difficulty": "{session["difficulty"]}",
  "intent": "질문 의도",
  "evaluation_points": "평가 포인트",
  "answer_guide": "답변 가이드"
}}
""".strip()


def build_feedback_prompt(item: dict) -> str:
    return f"""
당신은 면접 답변 코치입니다.
아래 질문과 지원자 답변을 평가해 주세요.

[질문]
{item.get("question", "")}

[질문 의도]
{item.get("intent", "")}

[평가 포인트]
{item.get("evaluation_points", "")}

[답변 가이드]
{item.get("answer_guide", "")}

[지원자 답변]
{item.get("answer", "")}

[작성 규칙]
1. 점수는 100점 만점의 정수로 주세요.
2. 장점과 개선점을 구체적으로 작성하세요.
3. 반드시 아래 JSON 형식만 반환하세요.

{{
  "score": 0,
  "strength": "잘한 점",
  "improvement": "개선할 점",
  "model_answer": "더 좋은 답변 예시"
}}
""".strip()


def fallback_question(session: dict) -> dict:
    profile_text = _profile_text(session["profile"]).lower()
    question_type = _question_type(session)
    difficulty = session["difficulty"]

    if "data" in profile_text or "sql" in profile_text or "분석" in profile_text:
        question = "최근 진행한 데이터 분석 경험에서 가장 어려웠던 문제와, 그 문제를 해결하기 위해 어떤 판단을 했는지 설명해 주세요."
        points = "문제 정의, 데이터 접근 방식, 분석 결과를 실제 의사결정에 연결한 경험"
    elif "개발" in profile_text or "python" in profile_text or "프로젝트" in profile_text:
        question = "지원 직무와 가장 관련 있는 프로젝트 하나를 선택해 본인의 역할, 기술적 선택, 결과를 구체적으로 설명해 주세요."
        points = "역할 명확성, 기술 선택의 근거, 문제 해결 과정, 결과 수치화"
    else:
        question = "지원 직무에서 본인이 가장 빠르게 기여할 수 있는 강점은 무엇이며, 그 근거가 되는 경험을 설명해 주세요."
        points = "직무 이해도, 경험의 구체성, 강점과 직무 요구사항의 연결"

    if session["mode"] == "실전 모드" and session["current_index"] >= 7:
        question = "방금 답변한 경험이 우리 회사의 실제 업무 상황에서도 통한다고 볼 수 있는 근거는 무엇인가요?"
        question_type = "꼬리 질문"

    return InterviewItem(
        question=question,
        question_type=question_type,
        difficulty=difficulty,
        intent="지원자의 경험과 직무 역량이 실제 업무에 연결되는지 확인합니다.",
        evaluation_points=points,
        answer_guide="상황, 본인 행동, 결과, 배운 점을 순서대로 말하면 답변의 설득력이 높아집니다.",
    ).__dict__


def fallback_feedback(item: dict) -> dict[str, str | int]:
    answer = (item.get("answer") or "").strip()
    score = min(92, max(58, 55 + len(answer) // 8))
    has_result = any(token in answer for token in ["결과", "성과", "%", "증가", "감소", "개선"])
    has_action = any(token in answer for token in ["제가", "분석", "설계", "구현", "정리", "제안"])

    improvement = "경험의 배경, 본인의 행동, 결과를 더 분명히 나누면 좋습니다."
    if not has_result:
        improvement = "결과나 성과를 수치, 변화, 피드백 형태로 덧붙이면 답변이 더 강해집니다."
    elif not has_action:
        improvement = "팀의 결과뿐 아니라 본인이 직접 맡은 판단과 행동을 더 강조해 주세요."

    return {
        "score": score,
        "strength": "지원 경험을 바탕으로 답변하려는 방향이 좋습니다.",
        "improvement": improvement,
        "model_answer": "저는 문제 상황을 먼저 정의한 뒤, 제가 맡은 역할과 선택한 방법을 설명하고, 마지막에 결과와 배운 점을 연결해 답변하겠습니다.",
    }


def generate_question(session: dict) -> tuple[dict | None, str]:
    try:
        if os.getenv("OPENAI_API_KEY"):
            data = _call_generation_llm(build_question_prompt(session))
        else:
            data = fallback_question(session)
    except Exception:
        data = fallback_question(session)

    item = InterviewItem(
        question=str(data.get("question", "")).strip(),
        question_type=str(data.get("question_type") or _question_type(session)).strip(),
        difficulty=str(data.get("difficulty") or session["difficulty"]).strip(),
        intent=str(data.get("intent", "")).strip(),
        evaluation_points=str(data.get("evaluation_points", "")).strip(),
        answer_guide=str(data.get("answer_guide", "")).strip(),
    ).__dict__

    if not item["question"]:
        return None, "질문을 생성하지 못했습니다. 입력 정보를 조금 더 구체적으로 적고 다시 시도해 주세요."
    return item, ""


def generate_feedback(item: dict) -> dict[str, str | int]:
    try:
        if os.getenv("OPENAI_API_KEY"):
            data = _call_generation_llm(build_feedback_prompt(item))
        else:
            data = fallback_feedback(item)
    except Exception:
        data = fallback_feedback(item)
    return {
        "score": data.get("score", "-"),
        "strength": str(data.get("strength", "")).strip(),
        "improvement": str(data.get("improvement", "")).strip(),
        "model_answer": str(data.get("model_answer", "")).strip(),
    }


def format_question(session: dict) -> str:
    if not session.get("items"):
        return "지원 정보를 입력하고 면접 세션을 시작해 주세요."

    item = session["items"][session["current_index"]]
    return f"""
### 질문 {session["current_index"] + 1} / {session["total_questions"]}

{item["question"]}

<div class="question-meta">
  <span>{item["question_type"]}</span>
  <span>{item["difficulty"]}</span>
</div>
""".strip()


def format_feedback(item: dict) -> str:
    feedback = item.get("feedback") or {}
    return f"""
### 답변 피드백

- 점수: **{feedback.get("score", "-")} / 100**
- 잘한 점: {feedback.get("strength", "")}
- 개선할 점: {feedback.get("improvement", "")}

### 답변 가이드

- 질문 의도: {item.get("intent", "")}
- 평가 포인트: {item.get("evaluation_points", "")}
- 답변 방향: {item.get("answer_guide", "")}

### 예시 답변

{feedback.get("model_answer", "")}
""".strip()


def format_progress(session: dict) -> str:
    if not session.get("items"):
        return ""
    answered = sum(1 for item in session["items"] if item.get("answer"))
    return f"진행 상황: {answered} / {session['total_questions']}개 답변 완료"


def format_report(session: dict) -> str:
    scores = [
        int(item.get("feedback", {}).get("score"))
        for item in session.get("items", [])
        if str(item.get("feedback", {}).get("score", "")).isdigit()
    ]
    average = round(sum(scores) / len(scores), 1) if scores else "-"
    lines = [
        "## 면접 세션 리포트",
        "",
        f"- 세션 ID: `{session.get('session_id', '')}`",
        f"- 모드: {session.get('mode', '')}",
        f"- 평균 점수: **{average} / 100**",
        f"- 시작: {session.get('started_at', '')}",
        f"- 종료: {session.get('ended_at') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    for index, item in enumerate(session.get("items", []), start=1):
        lines.extend(
            [
                f"### {index}. {item.get('question', '')}",
                f"- 답변: {item.get('answer', '') or '미답변'}",
                f"- 점수: {item.get('feedback', {}).get('score', '-')}",
                f"- 개선할 점: {item.get('feedback', {}).get('improvement', '')}",
                "",
            ]
        )
    return "\n".join(lines)


def start_session(
    education: str,
    target_job: str,
    skills: str,
    experiences: str,
    certs: str,
    memo: str,
    mode: str,
    difficulty: str,
):
    profile = {
        "education": (education or "").strip(),
        "target_job": (target_job or "").strip(),
        "skills": _split_csv(skills),
        "experiences": (experiences or "").strip(),
        "certs": _split_csv(certs),
        "memo": (memo or "").strip(),
    }
    is_valid, message = validate_profile(profile)
    if not is_valid:
        return (
            empty_session(),
            "지원 정보를 보완해 주세요.",
            gr.update(value="", interactive=False),
            message,
            "",
            "",
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(interactive=False),
        )

    session = {
        **empty_session(),
        "active": True,
        "session_id": uuid4().hex[:12],
        "mode": mode,
        "difficulty": "자동" if mode == "실전 모드" else difficulty,
        "profile": profile,
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_questions": REAL_TOTAL if mode == "실전 모드" else PRACTICE_TOTAL,
    }
    question, error = generate_question(session)
    if error:
        return (
            session,
            "질문 생성 실패",
            gr.update(value="", interactive=False),
            error,
            "",
            "",
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(interactive=False),
        )
    session["items"].append(question)
    return (
        session,
        format_question(session),
        gr.update(value="", interactive=True),
        "답변을 입력한 뒤 제출해 주세요.",
        format_progress(session),
        "",
        gr.update(visible=False),
        gr.update(visible=True),
        gr.update(interactive=True),
    )


def submit_answer(answer: str, session: dict):
    if not session or not session.get("active"):
        return (
            session,
            "진행 중인 세션이 없습니다.",
            gr.update(interactive=False),
            "먼저 면접 세션을 시작해 주세요.",
            "",
            "",
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(interactive=False),
        )

    cleaned = (answer or "").strip()
    if len(cleaned) < 10:
        return (
            session,
            format_question(session),
            gr.update(interactive=True),
            "실제 면접처럼 최소 두 문장 정도로 답변해 주세요.",
            format_progress(session),
            "",
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(interactive=True),
        )

    item = session["items"][session["current_index"]]
    item["answer"] = cleaned
    item["feedback"] = generate_feedback(item)

    is_last = session["current_index"] + 1 >= session["total_questions"]
    feedback_text = "" if session["mode"] == "실전 모드" and not is_last else format_feedback(item)

    if is_last:
        session["active"] = False
        session["ended_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return (
            session,
            "면접 세션이 종료되었습니다.",
            gr.update(value="", interactive=False),
            "모든 질문에 답변했습니다. 아래 리포트를 확인해 주세요.",
            format_progress(session),
            format_report(session),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(interactive=False),
        )

    status = (
        "답변이 저장되었습니다. 준비되면 다음 질문으로 이동하세요."
        if session["mode"] == "실전 모드"
        else "피드백을 확인한 뒤 다음 질문으로 이동하세요."
    )
    return (
        session,
        format_question(session),
        gr.update(interactive=False),
        status,
        format_progress(session),
        feedback_text,
        gr.update(visible=True),
        gr.update(visible=True),
        gr.update(interactive=False),
    )


def next_question(session: dict):
    if not session or not session.get("active"):
        return (
            session,
            "진행 중인 세션이 없습니다.",
            gr.update(value="", interactive=False),
            "먼저 면접 세션을 시작해 주세요.",
            format_progress(session or empty_session()),
            "",
            gr.update(visible=False),
            gr.update(interactive=False),
        )

    current = session["items"][session["current_index"]]
    if not current.get("answer"):
        return (
            session,
            format_question(session),
            gr.update(interactive=True),
            "현재 질문에 먼저 답변해 주세요.",
            format_progress(session),
            "",
            gr.update(visible=False),
            gr.update(interactive=True),
        )

    session["current_index"] += 1
    if len(session["items"]) <= session["current_index"]:
        question, error = generate_question(session)
        if error:
            session["current_index"] -= 1
            return (
                session,
                format_question(session),
                gr.update(interactive=False),
                error,
                format_progress(session),
                "",
                gr.update(visible=True),
                gr.update(interactive=False),
            )
        session["items"].append(question)

    return (
        session,
        format_question(session),
        gr.update(value="", interactive=True),
        "답변을 입력한 뒤 제출해 주세요.",
        format_progress(session),
        "",
        gr.update(visible=False),
        gr.update(interactive=True),
    )


def update_difficulty_visibility(mode: str):
    return gr.update(visible=mode == "연습 모드")


CSS = """
@font-face{
  font-family:"Chiron Go Round TC";
  src:url("/gradio_api/file=assets/fonts/ChironGoRoundTC-VariableFont_wght.ttf") format("truetype");
  font-style:normal;
  font-weight:100 900;
  font-display:swap;
}
:root{
  --ink:#172033;
  --muted:#687386;
  --glass-border:rgba(255,255,255,.82);
  --glass-fill:rgba(247,250,255,.56);
  --glass-shadow:0 22px 50px rgba(62,77,108,.18),0 6px 14px rgba(49,75,121,.12);
}
html,body{min-height:100%;background:#e7e8ea!important}
.gradio-container{
  max-width:none!important;
  min-height:100vh!important;
  margin:0!important;
  padding:24px!important;
  color:var(--ink)!important;
  font-family:"Chiron Go Round TC",sans-serif!important;
  background:
    linear-gradient(rgba(103,112,125,.055) 1px,transparent 1px),
    linear-gradient(90deg,rgba(103,112,125,.055) 1px,transparent 1px),
    linear-gradient(135deg,#dfe1e4 0%,#f1f2f3 48%,#dfe1e5 100%)!important;
  background-size:32px 32px,32px 32px,auto!important;
}
.gradio-container *{font-family:"Chiron Go Round TC",sans-serif!important;letter-spacing:0!important}
.app-shell{max-width:1180px;margin:0 auto!important}
.hero{text-align:center;padding:8px 8px 22px}
.hero .eyebrow{
  display:inline-flex;padding:7px 13px;border-radius:999px;
  color:#49627f;font-size:12px;font-weight:750;
  border:1px solid rgba(255,255,255,.9);
  background:linear-gradient(145deg,rgba(255,255,255,.72),rgba(222,234,250,.48));
  box-shadow:inset 0 1px 1px #fff,0 7px 16px rgba(65,83,115,.12);
}
.hero h1{font-size:34px;margin:15px 0 8px;color:#141a25}
.hero p{margin:0;color:var(--muted);line-height:1.7;font-size:15px}
.glass-card,.panel{
  position:relative;
  overflow:hidden;
  padding:24px!important;
  border-radius:28px!important;
  border:1px solid var(--glass-border)!important;
  background:linear-gradient(145deg,rgba(255,255,255,.56),rgba(224,227,232,.36))!important;
  -webkit-backdrop-filter:blur(26px) saturate(145%);
  backdrop-filter:blur(26px) saturate(145%);
  box-shadow:inset 0 2px 2px rgba(255,255,255,.96),inset 0 -2px 4px rgba(83,93,108,.2),var(--glass-shadow)!important;
}
.glass-card>.block,.glass-card>.form,.panel>.block,.panel>.form{
  border:0!important;background:transparent!important;box-shadow:none!important;
}
.gradio-container label span{color:#344054!important;font-weight:650!important;font-size:13px!important}
.gradio-container input,.gradio-container textarea{
  border-radius:16px!important;color:var(--ink)!important;
  border:1px solid rgba(144,166,201,.42)!important;
  background:linear-gradient(145deg,rgba(245,249,255,.74),rgba(255,255,255,.42))!important;
  box-shadow:inset 0 2px 4px rgba(68,91,127,.09),inset 0 -1px 1px rgba(255,255,255,.88),0 1px 0 rgba(255,255,255,.9)!important;
}
.gradio-container input:focus,.gradio-container textarea:focus{
  border-color:rgba(72,136,245,.72)!important;
  box-shadow:0 0 0 4px rgba(75,147,255,.13)!important;
}
.primary3d,.secondary3d{
  min-height:48px!important;border-radius:18px!important;font-weight:750!important;
  transition:transform .16s ease,box-shadow .16s ease,filter .16s ease!important;
}
.primary3d{
  color:#fff!important;border:1px solid rgba(255,255,255,.7)!important;
  background:linear-gradient(180deg,#73b8ff 0%,#3f8cf4 48%,#2469dc 100%)!important;
  box-shadow:inset 0 2px 2px rgba(255,255,255,.86),inset 0 -4px 8px rgba(24,73,169,.24),0 5px 0 rgba(35,86,174,.42),0 13px 24px rgba(50,111,220,.25)!important;
}
.secondary3d{
  color:#29466f!important;border:1px solid rgba(255,255,255,.82)!important;
  background:linear-gradient(145deg,rgba(255,255,255,.75),rgba(220,232,249,.5))!important;
  box-shadow:inset 0 2px 2px rgba(255,255,255,.94),inset 0 -2px 4px rgba(85,111,153,.13),0 4px 0 rgba(129,151,184,.25),0 9px 18px rgba(64,80,109,.13)!important;
}
.primary3d:hover,.secondary3d:hover{filter:brightness(1.035);transform:translateY(-1px)}
.primary3d:active,.secondary3d:active{transform:translateY(3px)}
.question-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.question-meta span{
  display:inline-flex;padding:6px 10px;border-radius:999px;font-size:12px;font-weight:700;
  color:#285d9f;background:rgba(204,226,255,.72);border:1px solid rgba(255,255,255,.9)
}
.status-chip,.progress-chip{
  padding:10px 14px!important;border-radius:18px!important;color:#43516a!important;
  border:1px solid rgba(255,255,255,.78)!important;
  background:linear-gradient(145deg,rgba(255,255,255,.6),rgba(224,235,250,.42))!important;
}
footer{display:none!important}
@media(max-width:760px){
  .gradio-container{padding:12px!important;background-size:24px 24px,24px 24px,auto!important}
  .hero h1{font-size:27px}
  .glass-card,.panel{padding:18px!important;border-radius:24px!important}
}
"""


with gr.Blocks(title=APP_TITLE) as demo:
    session_state = gr.State(empty_session())

    with gr.Column(elem_classes=["app-shell"]):
        gr.HTML(
            '<section class="hero">'
            '<span class="eyebrow">INTERVIEW QUESTION BUILDER</span>'
            f"<h1>{APP_TITLE}</h1>"
            "<p>지원 정보를 바탕으로 연습 면접과 실전 면접 질문을 생성하고 답변 피드백까지 이어갑니다.</p>"
            "</section>"
        )

        with gr.Row():
            with gr.Column(scale=4):
                with gr.Group(elem_classes=["glass-card"]):
                    gr.Markdown("### 지원 정보")
                    education = gr.Textbox(label="학력/전공", placeholder="예: 컴퓨터공학과, 경영학과")
                    target_job = gr.Textbox(label="지원 직무", placeholder="예: 데이터 분석, 백엔드 개발, 금융 IT")
                    skills = gr.Textbox(label="보유 기술", placeholder="쉼표로 구분: Python, SQL, Tableau")
                    certs = gr.Textbox(label="보유 자격증", placeholder="쉼표로 구분: SQLD, ADsP")
                    experiences = gr.Textbox(
                        label="프로젝트/경험",
                        lines=5,
                        placeholder="프로젝트 배경, 맡은 역할, 사용 기술, 결과를 간단히 적어 주세요.",
                    )
                    memo = gr.Textbox(
                        label="추가 메모",
                        lines=3,
                        placeholder="지원 회사, 산업군, 걱정되는 질문 유형 등을 적어도 좋습니다.",
                    )
                    with gr.Row():
                        mode = gr.Radio(
                            choices=["연습 모드", "실전 모드"],
                            value="연습 모드",
                            label="면접 모드",
                        )
                        difficulty = gr.Radio(
                            choices=["쉬움", "보통", "어려움"],
                            value="보통",
                            label="질문 난이도",
                        )
                    start_btn = gr.Button("세션 시작", variant="primary", elem_classes=["primary3d"])

            with gr.Column(scale=5):
                with gr.Group(elem_classes=["panel"]):
                    question_box = gr.Markdown("지원 정보를 입력하고 면접 세션을 시작해 주세요.")
                    answer_box = gr.Textbox(
                        label="답변",
                        lines=7,
                        interactive=False,
                        placeholder="현재 질문에 대한 답변을 입력하세요.",
                    )
                    with gr.Row():
                        submit_btn = gr.Button(
                            "답변 제출",
                            variant="primary",
                            interactive=False,
                            elem_classes=["primary3d"],
                        )
                        next_btn = gr.Button(
                            "다음 질문",
                            visible=False,
                            elem_classes=["secondary3d"],
                        )

        status_box = gr.Markdown("", elem_classes=["status-chip"])
        progress_box = gr.Markdown("", elem_classes=["progress-chip"])
        feedback_box = gr.Markdown("")
        report_box = gr.Markdown("")

    mode.change(update_difficulty_visibility, inputs=mode, outputs=difficulty)
    start_btn.click(
        start_session,
        inputs=[education, target_job, skills, experiences, certs, memo, mode, difficulty],
        outputs=[
            session_state,
            question_box,
            answer_box,
            status_box,
            progress_box,
            feedback_box,
            next_btn,
            submit_btn,
            submit_btn,
        ],
    )
    submit_btn.click(
        submit_answer,
        inputs=[answer_box, session_state],
        outputs=[
            session_state,
            question_box,
            answer_box,
            status_box,
            progress_box,
            feedback_box,
            next_btn,
            submit_btn,
            submit_btn,
        ],
    )
    next_btn.click(
        next_question,
        inputs=session_state,
        outputs=[
            session_state,
            question_box,
            answer_box,
            status_box,
            progress_box,
            feedback_box,
            next_btn,
            submit_btn,
        ],
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7861"))
    demo.queue(default_concurrency_limit=8).launch(
        server_name="0.0.0.0",
        server_port=port,
        show_error=False,
        css=CSS,
    )
