"""자소서 피드백 Tool.

공통 계약(README.md / AGENTS.md / 통합_PRD.md 7장):
- 외부 노출은 ``NAME`` 과 ``run(profile, user_input) -> str`` 둘뿐이다.
- ``user_input`` 은 **자소서 본문**으로 간주한다.
- 6개 평가 항목(문항부합·두괄식/STAR·직무연관성·구체성·차별성·가독성)으로 진단한다.
- 규칙 신호로 점수화한 뒤, OpenAI 키가 있으면 LLM 자연어 피드백을 생성하고
  없으면 규칙 기반 폴백 피드백을 반환한다. RAG/Chroma·런타임 외부 HTTP는 쓰지 않는다.
- 항상 사람이 읽을 문자열 하나를 반환한다. 예외도 내부에서 잡아 안내 문자열로 바꾼다.
- ``profile`` 은 읽기 전용 — 절대 수정하지 않는다.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.schema import UserProfile

NAME = "자소서 피드백"

# 본문이 이보다 짧으면 진단 대신 추가 입력을 요청한다(PRD 7.6).
MIN_BODY_LENGTH = 100

# 진단 항목 정의: (id, 표시명, 설명) — PRD 7.4 와 동일한 순서·정의.
CRITERIA: tuple[tuple[str, str, str], ...] = (
    ("intent", "문항 부합", "질문에 실제로 답하고 있는지"),
    ("structure", "두괄식/STAR", "결론 우선과 상황·과제·행동·결과 구조"),
    ("relevance", "직무 연관성", "지원 직무 역량과 본문의 연결"),
    ("specificity", "구체성/정량화", "숫자와 구체적 사례 제시"),
    ("uniqueness", "차별성", "본인만의 고유 경험 여부"),
    ("readability", "가독성", "문장 길이·클리셰·반복"),
)

# 정량 표현 신호: 숫자, %, 금액, 인원/건수/배수/기간 등.
_NUMBER_PATTERN = re.compile(
    r"\d+\s*(?:%|％|퍼센트|명|건|배|개|회|원|만원|억|년|개월|주|시간|등|위|점|위안|달러)?"
)
_PERCENT_PATTERN = re.compile(r"\d+\s*(?:%|％|퍼센트)")

# 결론·결과를 알리는 신호 표현(두괄식/STAR).
RESULT_WORDS = (
    "결과", "성과", "달성", "개선", "향상", "증가", "감소", "절감", "단축",
    "수상", "선정", "합격", "완성", "도출", "기여", "해결",
)
CONCLUSION_LEAD_WORDS = (
    "저는", "제가", "결론적으로", "핵심은", "가장", "무엇보다", "이를 통해",
)

# 추상적 클리셰(차별성·가독성 감점 신호).
CLICHE_WORDS = (
    "열정", "최선을 다", "책임감", "성실", "소통", "도전정신", "긍정적",
    "노력", "협력", "꼼꼼", "끈기", "적극적", "능동적", "원만한",
)

# 본문이 자소서가 아닐 가능성을 보는 신호(질문/명령형 위주면 추가 안내).
NON_ESSAY_HINTS = ("알려줘", "추천해", "뭐가", "어떻게 해", "해줘")

LLM_SYSTEM_PROMPT = (
    "당신은 채용 자기소개서를 첨삭하는 전문 커리어 코치입니다. "
    "지원자의 자소서 본문과 규칙 기반 진단 신호를 함께 받습니다. "
    "신호를 근거로 6개 항목(문항 부합, 두괄식/STAR, 직무 연관성, 구체성/정량화, "
    "차별성, 가독성)을 진단·강점·개선 방향으로 평가하세요. "
    "자소서에 없는 경험이나 성과를 새로 지어내지 말고, 한국어 존댓말로 실용적으로 작성하세요."
)


def _profile_value(profile: Any, field: str) -> Any:
    """UserProfile(또는 dict)에서 필드를 안전하게 읽는다. profile은 수정하지 않는다."""
    if isinstance(profile, dict):
        return profile.get(field, "")
    return getattr(profile, field, "")


def _as_text(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(item) for item in value if item)
    return str(value or "")


def _job_keywords(profile: Any) -> list[str]:
    """직무 연관성 판단에 쓸 키워드(희망 직무 + 보유 기술)."""
    raw = " ".join(
        [
            _as_text(_profile_value(profile, "target_job")),
            _as_text(_profile_value(profile, "skills")),
        ]
    )
    tokens = re.split(r"[\s,/·]+", raw)
    keywords: list[str] = []
    for token in tokens:
        cleaned = token.strip().lower()
        if len(cleaned) >= 2 and cleaned not in keywords:
            keywords.append(cleaned)
    return keywords


def _split_sentences(body: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+|\n+", body)
    return [part.strip() for part in parts if part.strip()]


def _count_occurrences(body: str, words: tuple[str, ...]) -> int:
    return sum(body.count(word) for word in words)


def _analyze(body: str, profile: Any, user_input: str) -> dict[str, Any]:
    """본문에서 규칙 신호를 추출한다. (LLM·폴백 양쪽이 공유)"""
    sentences = _split_sentences(body)
    sentence_count = len(sentences) or 1
    long_sentences = [s for s in sentences if len(s) >= 90]
    numbers = _NUMBER_PATTERN.findall(body)
    has_number = bool(re.search(r"\d", body))
    has_percent = bool(_PERCENT_PATTERN.search(body))

    result_hits = _count_occurrences(body, RESULT_WORDS)
    head = body[:120]
    has_conclusion_lead = any(word in head for word in CONCLUSION_LEAD_WORDS) or any(
        word in head for word in RESULT_WORDS
    )

    job_keywords = _job_keywords(profile)
    body_lower = body.lower()
    matched_jobs = [kw for kw in job_keywords if kw in body_lower]

    cliche_hits = _count_occurrences(body, CLICHE_WORDS)
    avg_sentence_len = len(body) / sentence_count

    # 자소서로 보기 어려운 짧은 명령형 입력 신호.
    looks_like_request = (
        len(body) < 200
        and any(hint in body for hint in NON_ESSAY_HINTS)
        and result_hits == 0
        and not has_number
    )

    return {
        "length": len(body),
        "sentence_count": sentence_count,
        "long_sentences": long_sentences,
        "numbers": numbers,
        "has_number": has_number,
        "has_percent": has_percent,
        "result_hits": result_hits,
        "has_conclusion_lead": has_conclusion_lead,
        "job_keywords": job_keywords,
        "matched_jobs": matched_jobs,
        "cliche_hits": cliche_hits,
        "avg_sentence_len": avg_sentence_len,
        "looks_like_request": looks_like_request,
        "target_job": _as_text(_profile_value(profile, "target_job")).strip(),
        "user_input_excerpt": user_input.strip(),
    }


def _criterion_feedback(criterion_id: str, signals: dict[str, Any]) -> dict[str, str]:
    """규칙 신호로 항목별 진단/강점/개선 방향을 만든다(폴백용)."""
    target_job = signals["target_job"] or "지원 직무"

    if criterion_id == "intent":
        if signals["looks_like_request"]:
            return {
                "진단": "자소서 본문보다 요청·질문에 가까운 글로 보입니다.",
                "강점": "전달하려는 의도가 분명합니다.",
                "개선 방향": "특정 문항(예: 지원동기, 성장과정)에 답하는 형태로 작성해 주세요.",
            }
        return {
            "진단": "문항이 함께 제시되지 않아 본문만으로 부합 여부를 추정했습니다.",
            "강점": "하나의 주제로 글이 이어지고 있습니다.",
            "개선 방향": "어떤 문항에 대한 답인지 명시하면 더 정확한 피드백이 가능합니다.",
        }

    if criterion_id == "structure":
        if signals["has_conclusion_lead"] and signals["result_hits"] > 0:
            return {
                "진단": "결론을 앞세우고 결과까지 언급하는 두괄식 흐름이 보입니다.",
                "강점": "STAR 중 결과(Result)가 드러납니다.",
                "개선 방향": "상황·과제·행동(S·T·A)을 한 문장씩 명확히 구분하면 더 탄탄해집니다.",
            }
        if not signals["has_conclusion_lead"]:
            return {
                "진단": "도입부에 결론·핵심 메시지가 약해 두괄식이 부족합니다.",
                "강점": "경험을 시간 순으로 풀어가는 점은 읽기에 자연스럽습니다.",
                "개선 방향": "첫 문장에 핵심 결론을 먼저 제시하는 두괄식으로 바꿔 보세요.",
            }
        return {
            "진단": "결론은 있으나 결과(Result)가 약합니다.",
            "강점": "주장을 먼저 제시하는 시도가 보입니다.",
            "개선 방향": "행동이 어떤 결과로 이어졌는지 마무리 문장에 추가하세요.",
        }

    if criterion_id == "relevance":
        if signals["matched_jobs"]:
            joined = ", ".join(signals["matched_jobs"][:3])
            return {
                "진단": f"{target_job} 관련 키워드({joined})가 본문에 나타납니다.",
                "강점": "지원 직무와 경험의 연결 고리가 있습니다.",
                "개선 방향": "직무에서 실제로 쓰는 도구·업무로 한 단계 더 구체화해 보세요.",
            }
        return {
            "진단": f"본문에서 {target_job} 직무와 직접 연결되는 표현을 찾기 어렵습니다.",
            "강점": "경험 자체는 설명되어 있습니다.",
            "개선 방향": "지원 직무의 핵심 역량 용어를 본문에 명시적으로 연결하세요.",
        }

    if criterion_id == "specificity":
        if signals["has_percent"] or len(signals["numbers"]) >= 3:
            return {
                "진단": "수치·정량 표현이 충분히 포함되어 있습니다.",
                "강점": "성과를 숫자로 입증하려는 점이 돋보입니다.",
                "개선 방향": "수치의 기준(기간·비교 대상)을 함께 적으면 설득력이 커집니다.",
            }
        if signals["has_number"]:
            return {
                "진단": "숫자가 일부 있지만 성과를 정량화한 표현은 부족합니다.",
                "강점": "사례를 들어 설명하려는 시도가 보입니다.",
                "개선 방향": "결과를 %·건수·기간 등 측정 가능한 수치로 바꿔 보세요.",
            }
        return {
            "진단": "정량 표현이 거의 없어 추상적으로 읽힙니다.",
            "강점": "경험의 맥락은 전달됩니다.",
            "개선 방향": "한 문장이라도 '몇 % 개선', '며칠 단축'처럼 수치로 제시하세요.",
        }

    if criterion_id == "uniqueness":
        if signals["cliche_hits"] >= 3:
            return {
                "진단": "추상적 표현(열정·책임감 등)이 반복되어 차별성이 약합니다.",
                "강점": "강조하고 싶은 태도는 분명합니다.",
                "개선 방향": "추상어 대신 본인만의 구체적 일화로 그 태도를 보여 주세요.",
            }
        return {
            "진단": "본인 경험을 중심으로 서술하려는 시도가 보입니다.",
            "강점": "일반론보다 개인 사례 비중이 있습니다.",
            "개선 방향": "남들과 다른 의사결정·시행착오를 더 부각하면 차별성이 살아납니다.",
        }

    # readability
    long_count = len(signals["long_sentences"])
    if long_count >= 2 or signals["avg_sentence_len"] >= 80 or signals["cliche_hits"] >= 3:
        return {
            "진단": "긴 문장이나 클리셰가 있어 가독성이 떨어집니다.",
            "강점": "정보량 자체는 충분합니다.",
            "개선 방향": "긴 문장을 두세 문장으로 나누고 클리셰를 줄여 보세요.",
        }
    return {
        "진단": "문장 길이가 대체로 적절해 읽기 편합니다.",
        "강점": "문단 흐름이 무난합니다.",
        "개선 방향": "핵심 문장에 강세를 주면 가독성이 더 좋아집니다.",
    }


def _format_rule_feedback(signals: dict[str, Any]) -> str:
    target_job = signals["target_job"] or "희망 직무"
    lines = [
        "현재 자소서를 기준으로 항목별 피드백을 드립니다.",
        f"(분석 기준: 본문 {signals['length']}자 · 지원 직무 {target_job})",
        "",
    ]
    for index, (criterion_id, label, _desc) in enumerate(CRITERIA, start=1):
        feedback = _criterion_feedback(criterion_id, signals)
        lines.extend(
            [
                f"### {index}. {label}",
                f"- **진단:** {feedback['진단']}",
                f"- **강점:** {feedback['강점']}",
                f"- **개선 방향:** {feedback['개선 방향']}",
                "",
            ]
        )

    # 마무리 조언: 가장 시급한 항목을 신호 기반으로 안내.
    priorities: list[str] = []
    if not signals["has_number"]:
        priorities.append("정량 표현(숫자·%) 추가")
    if not signals["has_conclusion_lead"]:
        priorities.append("두괄식으로 결론 먼저 배치")
    if not signals["matched_jobs"] and signals["job_keywords"]:
        priorities.append(f"{target_job} 직무 키워드 연결")
    if signals["cliche_hits"] >= 3:
        priorities.append("클리셰 줄이고 구체 일화로 대체")
    advice = (
        "우선순위: " + ", ".join(priorities)
        if priorities
        else "전반적으로 균형이 잡혀 있어요. 결과 수치만 보강하면 더 좋아집니다."
    )
    lines.append(f"**마무리 조언:** {advice}")
    return "\n".join(lines)


def _build_llm_user_prompt(body: str, signals: dict[str, Any]) -> str:
    target_job = signals["target_job"] or "(미입력)"
    signal_summary = (
        f"- 본문 길이: {signals['length']}자\n"
        f"- 정량 표현 포함: {'예' if signals['has_number'] else '아니오'}"
        f" (퍼센트 표현: {'예' if signals['has_percent'] else '아니오'})\n"
        f"- 결론/결과 신호: {'있음' if signals['has_conclusion_lead'] else '약함'}"
        f" (결과 단어 {signals['result_hits']}회)\n"
        f"- 지원 직무 키워드 매칭: "
        f"{', '.join(signals['matched_jobs']) if signals['matched_jobs'] else '없음'}\n"
        f"- 클리셰 빈도: {signals['cliche_hits']}회\n"
        f"- 긴 문장 수(90자+): {len(signals['long_sentences'])}개\n"
    )
    return (
        f"[지원 직무]\n{target_job}\n\n"
        f"[규칙 기반 진단 신호]\n{signal_summary}\n"
        f"[자소서 본문]\n{body}\n\n"
        "위 신호를 근거로 6개 항목을 다음 형식으로 평가해 주세요.\n"
        "현재 자소서를 기준으로 항목별 피드백을 드립니다.\n\n"
        "1. 문항 부합\n- 진단:\n- 강점:\n- 개선 방향:\n\n"
        "2. 두괄식/STAR\n- 진단:\n- 강점:\n- 개선 방향:\n\n"
        "3. 직무 연관성\n- 진단:\n- 강점:\n- 개선 방향:\n\n"
        "4. 구체성/정량화\n- 진단:\n- 강점:\n- 개선 방향:\n\n"
        "5. 차별성\n- 진단:\n- 강점:\n- 개선 방향:\n\n"
        "6. 가독성\n- 진단:\n- 강점:\n- 개선 방향:\n\n"
        "마무리 조언:"
    )


def _llm_feedback(body: str, signals: dict[str, Any]) -> str | None:
    """OpenAI 키가 있으면 LLM 자연어 피드백을 반환. 실패 시 None(폴백 유도)."""
    import os

    if not os.getenv("OPENAI_API_KEY"):
        return None

    user_prompt = _build_llm_user_prompt(body, signals)

    # 1순위: 프로젝트 공통 langchain 래퍼.
    try:
        from core.llm import get_generation_llm

        llm = get_generation_llm()
        response = llm.invoke(
            [
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )
        text = getattr(response, "content", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
    except Exception:
        pass

    # 2순위: openai 클라이언트 직접 호출(app/api.py 패턴과 동일).
    try:
        from openai import OpenAI

        model = os.getenv("OPENAI_GENERATION_MODEL") or os.getenv("CHAT_MODEL", "gpt-4o-mini")
        response = OpenAI().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1200,
        )
        text = response.choices[0].message.content
        if isinstance(text, str) and text.strip():
            return text.strip()
    except Exception:
        return None

    return None


def _need_more_input_message(body: str) -> str:
    return (
        "자소서 본문이 짧아 피드백을 드리기 어려워요. "
        f"(현재 {len(body)}자 / 최소 {MIN_BODY_LENGTH}자 권장)\n\n"
        "아래 정보를 함께 입력해 주시면 6개 항목으로 진단해 드릴게요.\n"
        "- **자소서 문항** (예: 지원동기, 성장과정)\n"
        "- **자소서 본문** (100자 이상)\n"
        "- 강조하고 싶은 경험이 있다면 함께 적어 주세요.\n\n"
        "예: \"은행 IT 지원동기입니다. 저는 데이터 분석 동아리에서 ...\" 형태로 본문을 붙여넣어 주세요."
    )


def run(profile: UserProfile, user_input: str) -> str:
    """자소서 본문(user_input)을 6개 항목으로 진단한 피드백 문자열을 반환한다."""
    try:
        body = str(user_input or "").strip()
        if not body:
            return (
                "피드백할 자소서 본문을 입력해 주세요.\n"
                "지원 직무와 자소서 문항을 함께 적어 주시면 더 정확하게 진단해 드릴게요."
            )

        if len(body) < MIN_BODY_LENGTH:
            return _need_more_input_message(body)

        signals = _analyze(body, profile, user_input)

        llm_result = _llm_feedback(body, signals)
        if llm_result:
            return llm_result

        return _format_rule_feedback(signals)
    except Exception:
        # 내부 오류 상세·키를 노출하지 않고 안내 문자열로 마무리.
        return (
            "자소서를 분석하는 중 문제가 발생했어요. "
            "본문을 다시 붙여넣고 한 번 더 시도해 주세요."
        )
