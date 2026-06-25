"""면접 질문 생성 Tool.

공통 계약:
- 외부 노출은 ``NAME``(str)와 ``run(profile, user_input) -> str`` 둘뿐이다.
- ``profile``은 ``core.schema.UserProfile`` 인스턴스이며 읽기 전용이다.
- ``run``은 항상 사람이 읽을 문자열 하나를 반환한다. dict/None/예외를 노출하지 않는다.
- ``OPENAI_API_KEY``가 없어도 규칙 기반 폴백으로 문자열을 반환한다.

원본(origin/jiyu:면접생성툴.py)의 질문 생성 프롬프트·LLM 호출·규칙 기반
``fallback_question``·질문 유형 판정·포맷팅 로직을 재사용하되, Gradio 세션 기반
연속 대화 구조를 단발 호출 계약으로 단순화했다. 매 호출마다 profile + user_input
으로 면접 질문 3개를 독립적으로 생성한다.
"""

from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.schema import UserProfile

NAME = "면접 질문"

QUESTION_TYPES = ["인성", "직무", "프로젝트", "기업맞춤", "압박"]
NUM_QUESTIONS = 3

MODE_PRACTICE = "연습모드"
MODE_REAL = "실전모드"

# "1번 답변: ..." 또는 "답변: ..." 패턴
ANSWER_FEEDBACK_RE = re.compile(r"^(?:\d+번\s*)?답변\s*[:：]\s*(.+)", re.DOTALL | re.IGNORECASE)


# ---------------------------------------------------------------------------
# UserProfile 안전 접근 (읽기 전용)
# ---------------------------------------------------------------------------
def _profile_value(profile: Any, field: str) -> Any:
    if isinstance(profile, dict):
        return profile.get(field, "")
    return getattr(profile, field, "")


def _as_text(value: Any) -> str:
    """list/tuple/set/str 무엇이 와도 사람이 읽을 한 줄 문자열로."""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _profile_text(profile: Any) -> str:
    skills = _as_text(_profile_value(profile, "skills")) or "미입력"
    experiences = _as_text(_profile_value(profile, "experiences")) or "미입력"
    certs = _as_text(_profile_value(profile, "certs")) or "없음"
    education = _as_text(_profile_value(profile, "education")) or "미입력"
    target_job = _as_text(_profile_value(profile, "target_job")) or "미입력"
    return "\n".join(
        [
            f"학력/전공: {education}",
            f"지원 직무: {target_job}",
            f"보유 기술: {skills}",
            f"보유 자격증: {certs}",
            f"프로젝트/경험: {experiences}",
        ]
    )


# ---------------------------------------------------------------------------
# LLM 경로
# ---------------------------------------------------------------------------
def extract_json(text: str) -> Any:
    """LLM 응답에서 JSON(객체/배열)을 추출한다. (원본 extract_json 재사용)"""
    cleaned = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()
    match = re.search(r"(\[.*\]|\{.*\})", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


def build_questions_prompt(profile: Any, user_input: str) -> str:
    """면접 질문 3개를 한 번에 생성하는 프롬프트. (원본 build_question_prompt 기반)"""
    request = user_input.strip() or "지원 직무에 맞는 면접 질문을 만들어 주세요."
    types = ", ".join(QUESTION_TYPES)
    return f"""
당신은 실제 채용 면접관입니다.
지원자의 정보와 요청을 바탕으로 면접 질문 {NUM_QUESTIONS}개를 생성하세요.

[지원자 정보]
{_profile_text(profile)}

[지원자 요청]
{request}

[질문 유형 풀]
{types} (인성/직무/프로젝트/기업맞춤/압박)

[작성 규칙]
1. 질문은 서로 중복되지 않게 작성하세요.
2. 가능하면 위 유형을 다양하게 섞으세요.
3. 각 질문마다 질문 의도, 평가 포인트, 답변 가이드를 분리해 작성하세요.
4. 지원자의 직무·경험·기술을 반영해 구체적으로 작성하세요.
5. 반드시 아래 JSON 배열 형식만 반환하세요. (다른 텍스트 금지)

[
  {{
    "question": "면접 질문",
    "question_type": "{QUESTION_TYPES[0]}",
    "intent": "질문 의도",
    "evaluation_points": "평가 포인트",
    "answer_guide": "답변 가이드"
  }}
]
""".strip()


def _call_generation_llm(prompt: str) -> Any:
    """LLM 호출. 키가 없거나 모듈이 없으면 예외를 일으켜 폴백으로 넘긴다."""
    try:
        from core.llm import get_generation_llm

        llm = get_generation_llm()
    except ImportError:
        # 계약 호환용: 구현체가 get_llm만 노출하는 경우.
        from core.llm import get_llm  # type: ignore[attr-defined]

        llm = get_llm()
    response = llm.invoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)
    return extract_json(content)


def _normalize_items(raw: Any) -> list[dict[str, str]]:
    """LLM 응답을 질문 dict 리스트로 정규화한다."""
    if isinstance(raw, dict):
        # 단일 객체이거나 {"questions": [...]} 형태일 수 있다.
        if isinstance(raw.get("questions"), list):
            raw = raw["questions"]
        else:
            raw = [raw]
    if not isinstance(raw, list):
        return []

    items: list[dict[str, str]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        question = str(entry.get("question", "")).strip()
        if not question:
            continue
        items.append(
            {
                "question": question,
                "question_type": str(
                    entry.get("question_type")
                    or QUESTION_TYPES[index % len(QUESTION_TYPES)]
                ).strip(),
                "intent": str(entry.get("intent", "")).strip(),
                "evaluation_points": str(entry.get("evaluation_points", "")).strip(),
                "answer_guide": str(entry.get("answer_guide", "")).strip(),
            }
        )
    return items[:NUM_QUESTIONS]


# ---------------------------------------------------------------------------
# 규칙 기반 폴백 (원본 fallback_question 확장: 유형별 템플릿 3개)
# ---------------------------------------------------------------------------
_ANSWER_GUIDE = "상황·본인 행동·결과·배운 점을 순서대로 말하면 답변의 설득력이 높아집니다."


def _domain_question(profile: Any) -> tuple[str, str]:
    """프로필 텍스트로 직무 도메인을 추정해 직무 질문 1개를 만든다."""
    text = _profile_text(profile).lower()
    if any(token in text for token in ("data", "sql", "분석", "데이터")):
        return (
            "최근 진행한 데이터 분석 경험에서 가장 어려웠던 문제와, 그 문제를 해결하기 위해 "
            "어떤 판단을 했는지 설명해 주세요.",
            "문제 정의, 데이터 접근 방식, 분석 결과를 실제 의사결정에 연결한 경험",
        )
    if any(token in text for token in ("개발", "python", "java", "backend", "백엔드", "서버")):
        return (
            "지원 직무와 가장 관련 있는 기술적 의사결정을 하나 골라, 어떤 대안을 검토했고 "
            "왜 그 선택을 했는지 설명해 주세요.",
            "기술 선택의 근거, 트레이드오프 이해, 문제 해결 과정",
        )
    return (
        "지원 직무에서 본인이 가장 빠르게 기여할 수 있는 강점은 무엇이며, 그 근거가 되는 "
        "경험을 설명해 주세요.",
        "직무 이해도, 경험의 구체성, 강점과 직무 요구사항의 연결",
    )


def fallback_questions(profile: Any, user_input: str) -> list[dict[str, str]]:
    """LLM 없이 규칙 기반으로 면접 질문 3개(직무/프로젝트/기업맞춤)를 만든다."""
    target_job = _as_text(_profile_value(profile, "target_job")) or "지원 직무"
    company = _extract_company(user_input) or "지원하신 회사"

    domain_q, domain_points = _domain_question(profile)
    items = [
        {
            "question": domain_q,
            "question_type": "직무",
            "intent": "지원자의 직무 역량이 실제 업무에 연결되는지 확인합니다.",
            "evaluation_points": domain_points,
            "answer_guide": _ANSWER_GUIDE,
        },
        {
            "question": (
                "지원 직무와 가장 관련 있는 프로젝트 하나를 선택해 본인의 역할, 기술적 선택, "
                "결과를 구체적으로 설명해 주세요."
            ),
            "question_type": "프로젝트",
            "intent": "경험을 구조화해 전달하는 능력과 실제 기여도를 확인합니다.",
            "evaluation_points": "역할 명확성, 기술 선택의 근거, 문제 해결 과정, 결과 수치화",
            "answer_guide": _ANSWER_GUIDE,
        },
        {
            "question": (
                f"{company}의 {target_job} 직무에 지원한 이유와, 입사 후 6개월 안에 만들고 싶은 "
                "성과를 말씀해 주세요."
            ),
            "question_type": "기업맞춤",
            "intent": "회사·직무에 대한 이해와 지원 동기의 진정성을 확인합니다.",
            "evaluation_points": "회사/직무 이해도, 지원 동기의 구체성, 목표의 현실성",
            "answer_guide": _ANSWER_GUIDE,
        },
    ]
    return items


def _extract_company(user_input: str) -> str:
    """user_input에서 '○○ 회사/기업' 형태의 지원 기업명을 단순 추출한다."""
    text = (user_input or "").strip()
    if not text:
        return ""
    match = re.search(r"([\w가-힣]+)\s*(?:회사|기업|에\s*지원|면접)", text)
    if match:
        candidate = match.group(1).strip()
        if candidate and candidate not in {"면접", "질문", "이", "그", "저"}:
            return candidate
    return ""


# ---------------------------------------------------------------------------
# 모드 파싱
# ---------------------------------------------------------------------------
def _parse_mode(user_input: str) -> tuple[str | None, str]:
    """[연습모드] 또는 [실전모드] 접두어를 분리. (mode|None, stripped_input) 반환."""
    m = re.match(r"^\[(연습모드|실전모드)\]\s*", user_input.strip())
    if m:
        return m.group(1), user_input[m.end():].strip()
    return None, user_input


# ---------------------------------------------------------------------------
# 답변 평가
# ---------------------------------------------------------------------------
def _evaluate_answer(answer: str, profile: Any) -> str:
    """면접 답변을 STAR·구체성·직무연관성 기준으로 평가한다."""
    if not answer or len(answer) < 10:
        return "답변 내용을 조금 더 길게 입력해 주세요."

    if os.getenv("OPENAI_API_KEY"):
        try:
            target_job = _as_text(_profile_value(profile, "target_job")) or "지원 직무"
            from openai import OpenAI
            model = os.getenv("CHAT_MODEL", "gpt-4o-mini")
            system = (
                "당신은 채용 면접관입니다. 지원자의 면접 답변을 아래 기준으로 평가하세요.\n"
                "평가 기준: STAR 구조(상황·과제·행동·결과), 구체성(수치·사례), 직무 연관성\n"
                "형식: **강점** 1~2개 / **개선 포인트** 1~2개 / **한 줄 종합 평가**\n"
                "간결하게, 한국어 존댓말로 작성하세요."
            )
            resp = OpenAI().chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"[지원 직무] {target_job}\n\n[답변]\n{answer}"},
                ],
                max_tokens=400,
            )
            text = resp.choices[0].message.content
            if text and text.strip():
                return text.strip()
        except Exception:
            pass

    # 규칙 기반 폴백
    has_number = bool(re.search(r"\d+\s*(?:%|명|건|배|개|년|개월|점|위)", answer))
    result_hits = sum(answer.count(w) for w in ("결과", "성과", "달성", "개선", "해결"))
    star_hits = sum(1 for w in ("상황", "과제", "행동", "결과") if w in answer)
    length = len(answer)

    strengths, improvements = [], []
    if star_hits >= 2:
        strengths.append("STAR 구조(상황·행동·결과)가 드러납니다.")
    if has_number:
        strengths.append("수치로 성과를 구체화했습니다.")
    if result_hits > 0:
        strengths.append("결과·성과를 언급해 답변을 마무리했습니다.")
    if length >= 100:
        strengths.append("충분한 분량으로 답변했습니다.")

    if not has_number:
        improvements.append("수치나 구체적 성과(%, 건수, 기간)를 추가하면 설득력이 높아집니다.")
    if result_hits == 0:
        improvements.append("행동이 가져온 결과나 배운 점을 마지막에 추가해 주세요.")
    if star_hits < 2:
        improvements.append("상황 → 과제 → 행동 → 결과(STAR) 흐름으로 구성하면 더 명확해집니다.")
    if length < 80:
        improvements.append("답변이 짧습니다. 구체적인 경험이나 사례를 추가해 주세요.")

    lines = ["**면접 답변 피드백**", ""]
    if strengths:
        lines += ["**강점**"] + [f"- {s}" for s in strengths] + [""]
    lines += ["**개선 포인트**"]
    if improvements:
        lines += [f"- {i}" for i in improvements]
    else:
        lines.append("- 전반적으로 잘 구성된 답변입니다. 실전에서도 자신 있게 말하세요!")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 포맷팅
# ---------------------------------------------------------------------------
def format_questions(
    items: list[dict[str, str]], profile: Any, via_llm: bool, mode: str = MODE_PRACTICE
) -> str:
    target_job = _as_text(_profile_value(profile, "target_job")) or "희망 직무"

    if mode == MODE_REAL:
        lines = [
            f"**{target_job}** 실전 면접을 시작합니다.",
            "가이드 없이 실제 면접처럼 답해보세요.", "",
        ]
        for index, item in enumerate(items, start=1):
            qtype = item.get("question_type") or "면접"
            lines.append(f"### Q{index}. [{qtype}]")
            lines.append(item["question"])
            lines.append("")
        lines.append("답변이 준비되면 **'1번 답변: [내용]'** 형식으로 입력해 주세요.")
    else:
        lines = [f"**{target_job}** 면접 예상 질문 {len(items)}개와 가이드를 준비했어요.", ""]
        for index, item in enumerate(items, start=1):
            qtype = item.get("question_type") or "면접"
            lines.append(f"### {index}. [{qtype}] {item['question']}")
            if item.get("intent"):
                lines.append(f"- **질문 의도:** {item['intent']}")
            if item.get("evaluation_points"):
                lines.append(f"- **평가 포인트:** {item['evaluation_points']}")
            if item.get("answer_guide"):
                lines.append(f"- **답변 가이드:** {item['answer_guide']}")
            lines.append("")
        lines.append("준비한 답변은 **'1번 답변: [내용]'** 형식으로 입력하면 피드백을 드릴게요.")

    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# 공개 진입점
# ---------------------------------------------------------------------------
def run(profile: UserProfile, user_input: str) -> str:
    """프로필과 사용자 요청으로 면접 질문 약 3개를 생성해 문자열로 반환한다."""
    try:
        user_input = str(user_input or "").strip()

        # [연습모드] / [실전모드] 접두어 파싱
        mode, user_input = _parse_mode(user_input)

        # 답변 피드백 요청 감지 ("1번 답변: ..." 또는 "답변: ...")
        answer_match = ANSWER_FEEDBACK_RE.match(user_input)
        if answer_match:
            return _evaluate_answer(answer_match.group(1).strip(), profile)

        target_job = _as_text(_profile_value(profile, "target_job"))
        experiences = _as_text(_profile_value(profile, "experiences"))
        skills = _as_text(_profile_value(profile, "skills"))
        if not (target_job or experiences or skills or user_input):
            return (
                "면접 질문을 만들려면 정보가 조금 더 필요해요.\n\n"
                "지원 직무나 주요 프로젝트/경험을 알려 주세요.\n"
                "예: **데이터 분석가로 지원, 고객 이탈 예측 프로젝트 경험 있음**"
            )

        items: list[dict[str, str]] = []
        via_llm = False
        if os.getenv("OPENAI_API_KEY"):
            try:
                raw = _call_generation_llm(build_questions_prompt(profile, user_input))
                items = _normalize_items(raw)
                via_llm = bool(items)
            except Exception:
                items = []

        if not items:
            items = fallback_questions(profile, user_input)

        if not items:
            return (
                "지금은 면접 질문을 생성하지 못했어요. "
                "지원 직무와 경험을 조금 더 구체적으로 알려 주시면 다시 만들어 드릴게요."
            )

        return format_questions(items, profile, via_llm, mode or MODE_PRACTICE)
    except Exception:
        return (
            "면접 질문을 생성하는 중 문제가 발생했어요. "
            "잠시 후 다시 시도하거나, 지원 직무와 경험을 다시 입력해 주세요."
        )
