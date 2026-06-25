from __future__ import annotations

import json
import re
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.schema import UserProfile

NAME = "자격증 추천"

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "certs.json"
MAX_RECOMMENDATIONS = 3
_RECOMMENDATION_HISTORY: OrderedDict[str, dict[str, list[str]]] = OrderedDict()
_MAX_HISTORY = 200

CATEGORY_ALIASES = {
    "금융": {"금융", "은행", "증권", "투자", "자산관리", "리스크"},
    "데이터": {"데이터", "분석", "sql", "db", "데이터베이스"},
    "IT": {"it", "개발", "개발자", "백엔드", "서버", "인프라", "네트워크"},
    "디지털": {"디지털", "핀테크", "플랫폼", "ai", "인공지능"},
    "사무·ERP": {"사무", "엑셀", "erp", "경영지원", "회계", "인사"},
}

SCHEDULE_WORDS = {
    "일정",
    "시험",
    "접수",
    "발표",
    "언제",
    "올해",
    "회차",
}
MORE_WORDS = {"더 추천", "다른 것도", "다른 자격증", "추가 추천", "또 추천"}
LIST_WORDS = {"목록", "종류", "전체", "뭐가 있어", "어떤 자격증"}


def _profile_value(profile: Any, field: str) -> Any:
    if isinstance(profile, dict):
        return profile.get(field, "")
    return getattr(profile, field, "")


def _normalize_text(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        value = " ".join(str(item) for item in value)
    text = str(value or "").lower().strip()
    text = re.sub(r"[\s_\-/]+", " ", text)
    return re.sub(r"[^0-9a-z가-힣· ]", "", text)


def _load_certificates() -> dict[str, Any]:
    try:
        with DATA_PATH.open(encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {"last_updated": None, "certificates": []}

    if not isinstance(payload, dict) or not isinstance(payload.get("certificates"), list):
        return {"last_updated": None, "certificates": []}
    return payload


def _alias_index(certificates: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    aliases: list[tuple[str, dict[str, Any]]] = []
    for certificate in certificates:
        names = [
            certificate.get("certificate_name", ""),
            certificate.get("certificate_id", ""),
            *certificate.get("aliases", []),
        ]
        for name in names:
            normalized = _normalize_text(name)
            if normalized:
                aliases.append((normalized, certificate))
    return sorted(aliases, key=lambda item: len(item[0]), reverse=True)


def _find_certificate(
    user_input: str, certificates: list[dict[str, Any]]
) -> dict[str, Any] | None:
    normalized_input = _normalize_text(user_input)
    compact_input = normalized_input.replace(" ", "")
    for alias, certificate in _alias_index(certificates):
        if alias in normalized_input or alias.replace(" ", "") in compact_input:
            return certificate
    return None


def _profile_key(profile: Any) -> str:
    session_id = _profile_value(profile, "session_id")
    if session_id:
        return f"session:{session_id}"
    parts = [
        _profile_value(profile, "education"),
        _profile_value(profile, "target_job"),
        _profile_value(profile, "skills"),
        _profile_value(profile, "certs"),
    ]
    return "|".join(_normalize_text(part) for part in parts)


def _remember(profile: Any, certificate_ids: list[str], reset: bool = False) -> None:
    key = _profile_key(profile)
    if reset or key not in _RECOMMENDATION_HISTORY:
        _RECOMMENDATION_HISTORY[key] = {"all": [], "last": []}
    history = _RECOMMENDATION_HISTORY[key]
    if reset:
        history["all"] = []
    for certificate_id in certificate_ids:
        if certificate_id not in history["all"]:
            history["all"].append(certificate_id)
    history["last"] = list(certificate_ids)
    _RECOMMENDATION_HISTORY.move_to_end(key)
    while len(_RECOMMENDATION_HISTORY) > _MAX_HISTORY:
        _RECOMMENDATION_HISTORY.popitem(last=False)


def _already_recommended(profile: Any) -> set[str]:
    history = _RECOMMENDATION_HISTORY.get(_profile_key(profile), {})
    return set(history.get("all", []))


def _last_recommended(profile: Any) -> list[str]:
    history = _RECOMMENDATION_HISTORY.get(_profile_key(profile), {})
    return list(history.get("last", []))


def _recent_recommendation_names(profile: Any) -> list[str]:
    """독립 Gradio 데모가 최근 추천 항목을 선택지로 표시할 때 사용한다."""
    certificates = _load_certificates().get("certificates", [])
    names = []
    for certificate_id in _last_recommended(profile):
        certificate = _certificate_by_id(certificate_id, certificates)
        if certificate:
            names.append(certificate["certificate_name"])
    return names


def _certificate_by_id(
    certificate_id: str, certificates: list[dict[str, Any]]
) -> dict[str, Any] | None:
    return next(
        (
            certificate
            for certificate in certificates
            if certificate.get("certificate_id") == certificate_id
        ),
        None,
    )


def _ordinal_index(user_input: str) -> int | None:
    normalized = _normalize_text(user_input).replace(" ", "")
    ordinal_groups = [
        ("첫번째", "첫째", "1번째", "1번"),
        ("두번째", "둘째", "2번째", "2번"),
        ("세번째", "셋째", "3번째", "3번"),
    ]
    for index, aliases in enumerate(ordinal_groups):
        if any(alias in normalized for alias in aliases):
            return index
    return None


def _resolve_recommended_schedule_request(
    profile: Any,
    user_input: str,
    certificates: list[dict[str, Any]],
    payload: dict[str, Any],
) -> str | None:
    if not _has_any(user_input, SCHEDULE_WORDS):
        return None

    recent_ids = _last_recommended(profile)
    if not recent_ids:
        return (
            "어떤 자격증의 시험 일정을 확인할까요?\n"
            "예: **SQLD 일정 알려줘**, **투운사 시험 일정 알려줘**"
        )

    recent = [
        certificate
        for certificate_id in recent_ids
        if (certificate := _certificate_by_id(certificate_id, certificates))
    ]
    if not recent:
        return None

    ordinal = _ordinal_index(user_input)
    if ordinal is not None:
        if ordinal < len(recent):
            return _format_schedule(recent[ordinal], payload, date.today().year)
        return f"최근 추천 목록에는 {len(recent)}개의 자격증만 있어요."

    normalized = _normalize_text(user_input)
    wants_all = any(
        phrase in normalized
        for phrase in ("모두", "전부", "각각", "추천한 자격증들", "추천해준 자격증들")
    )
    if wants_all:
        return "\n\n---\n\n".join(
            _format_schedule(certificate, payload, date.today().year)
            for certificate in recent
        )

    if len(recent) == 1:
        return _format_schedule(recent[0], payload, date.today().year)

    options = "\n".join(
        f"{index}. **{certificate['certificate_name']}**"
        for index, certificate in enumerate(recent, start=1)
    )
    return (
        "최근 추천한 자격증이 여러 개라서 확인이 필요해요.\n\n"
        f"{options}\n\n"
        '자격증명이나 번호를 함께 입력해 주세요. 예: **"1번 일정 알려줘"**'
    )


def _selected_category(user_input: str) -> str | None:
    normalized = _normalize_text(user_input)
    for category, keywords in CATEGORY_ALIASES.items():
        if any(_normalize_text(keyword) in normalized for keyword in keywords):
            return category
    return None


def _has_any(text: str, words: set[str]) -> bool:
    normalized = _normalize_text(text)
    return any(_normalize_text(word) in normalized for word in words)


def _profile_query(profile: Any, user_input: str) -> str:
    values = [
        _profile_value(profile, "education"),
        _profile_value(profile, "target_job"),
        _profile_value(profile, "skills"),
        _profile_value(profile, "experiences"),
        user_input,
    ]
    return _normalize_text(values)


def _owned_certificate_ids(
    profile: Any, certificates: list[dict[str, Any]]
) -> set[str]:
    owned_text = _normalize_text(_profile_value(profile, "certs"))
    owned_compact = owned_text.replace(" ", "")
    owned: set[str] = set()
    for certificate in certificates:
        for name in [
            certificate.get("certificate_name", ""),
            *certificate.get("aliases", []),
        ]:
            normalized = _normalize_text(name)
            if normalized and (
                normalized in owned_text
                or normalized.replace(" ", "") in owned_compact
            ):
                owned.add(certificate["certificate_id"])
                break
    return owned


def _rag_boosts(query: str) -> dict[str, int]:
    """통합 환경에 certs 컬렉션이 있으면 검색 순위를 보조한다."""
    try:
        from core.vectorstore import get_vectorstore

        docs = get_vectorstore("certs").similarity_search(query, k=6)
    except Exception:
        return {}

    boosts: dict[str, int] = {}
    for rank, document in enumerate(docs):
        metadata = getattr(document, "metadata", {}) or {}
        certificate_id = metadata.get("certificate_id")
        if certificate_id:
            boosts[str(certificate_id)] = max(1, 6 - rank)
    return boosts


def _score_certificates(
    profile: Any,
    user_input: str,
    certificates: list[dict[str, Any]],
    exclude: set[str],
) -> list[dict[str, Any]]:
    query = _profile_query(profile, user_input)
    selected_category = _selected_category(user_input)
    owned = _owned_certificate_ids(profile, certificates)
    rag_boosts = _rag_boosts(query)
    scored: list[tuple[int, int, str, dict[str, Any]]] = []

    for certificate in certificates:
        certificate_id = certificate["certificate_id"]
        if certificate_id in exclude or certificate_id in owned:
            continue

        score = 0
        matched: list[str] = []
        for keyword in certificate.get("keywords", []):
            normalized_keyword = _normalize_text(keyword)
            if normalized_keyword and normalized_keyword in query:
                score += 3
                matched.append(keyword)

        for related_job in certificate.get("related_jobs", []):
            normalized_job = _normalize_text(related_job)
            if normalized_job and normalized_job in query:
                score += 4
                matched.append(related_job)

        if selected_category and certificate.get("category") == selected_category:
            score += 3
        elif selected_category == "디지털" and certificate.get("category") in {"IT", "데이터"}:
            score += 2

        score += rag_boosts.get(certificate_id, 0)
        has_upcoming = any(
            _schedule_status(schedule) in {"접수 중", "예정"}
            for schedule in certificate.get("exams", [])
        )
        scored.append(
            (
                score,
                1 if has_upcoming else 0,
                certificate.get("certificate_name", ""),
                {**certificate, "_matched": matched[:3]},
            )
        )

    scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
    positive = [item[3] for item in scored if item[0] > 0]
    return positive[:MAX_RECOMMENDATIONS]


def _recommendation_reason(certificate: dict[str, Any], profile: Any) -> str:
    matched = certificate.get("_matched", [])
    target_job = str(_profile_value(profile, "target_job") or "").strip()
    if matched:
        basis = ", ".join(dict.fromkeys(matched))
        return f"{basis} 역량·관심과 연결되는 자격증입니다."
    if target_job:
        return f"{target_job} 직무 준비에 활용할 수 있는 자격증입니다."
    return certificate.get("description", "희망 직무 준비에 활용할 수 있습니다.")


def _format_recommendations(
    recommendations: list[dict[str, Any]], profile: Any, is_more: bool
) -> str:
    if not recommendations:
        if is_more:
            return (
                "현재 지원 범위에서 추가로 추천할 자격증이 없습니다. "
                "다른 직무나 분야를 입력해 주세요."
            )
        return (
            "추천에 필요한 정보가 조금 부족해요.\n\n"
            "어떤 직무로 취업을 준비하고 있나요?\n"
            "예: 은행·금융영업, 증권·자산운용, 데이터 분석, 금융 IT, 백엔드 개발"
        )

    target_job = str(_profile_value(profile, "target_job") or "희망 직무").strip()
    intro = (
        "추가로 준비할 수 있는 자격증을 추천해 드릴게요."
        if is_more
        else f"**{target_job}** 취업 준비에 도움이 되는 자격증을 추천해 드릴게요."
    )
    lines = [intro, ""]
    for index, certificate in enumerate(recommendations, start=1):
        jobs = ", ".join(certificate.get("related_jobs", [])[:3]) or "관련 직무 확인 필요"
        lines.extend(
            [
                f"### {index}. {certificate['certificate_name']}",
                f"- **분야:** {certificate.get('category', '미분류')}",
                f"- **추천 이유:** {_recommendation_reason(certificate, profile)}",
                f"- **관련 직무:** {jobs}",
                "",
            ]
        )
    lines.extend(
        [
            "관심 있는 자격증명을 입력하면 올해 시험 일정을 알려드릴게요.",
            '다른 자격증이 필요하면 **"더 추천해줘"**라고 입력해 주세요.',
        ]
    )
    return "\n".join(lines)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _schedule_status(schedule: dict[str, Any], today: date | None = None) -> str:
    today = today or date.today()
    application_start = _parse_date(schedule.get("application_start"))
    application_end = _parse_date(schedule.get("application_end"))
    exam_date = _parse_date(schedule.get("exam_date"))

    if application_start and application_end and application_start <= today <= application_end:
        return "접수 중"
    if exam_date and exam_date < today:
        return "종료"
    if exam_date and exam_date >= today:
        return "예정"
    if application_start and application_start > today:
        return "예정"
    return "일정 미정"


def _display_date(value: str | None) -> str:
    parsed = _parse_date(value)
    return parsed.strftime("%Y.%m.%d") if parsed else "아직 공시되지 않음"


def _display_period(start: str | None, end: str | None) -> str:
    if not start and not end:
        return "아직 공시되지 않음"
    return f"{_display_date(start)}~{_display_date(end)}"


def _schedule_table(schedules: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| 상태 | 회차 | 원서접수 기간 | 시험일 | 합격자 발표일 |",
        "|---|---|---|---|---|",
    ]
    for schedule in schedules:
        lines.append(
            "| {status} | {round_name} | {application} | {exam} | {result} |".format(
                status=_schedule_status(schedule),
                round_name=schedule.get("round") or "아직 공시되지 않음",
                application=_display_period(
                    schedule.get("application_start"),
                    schedule.get("application_end"),
                ),
                exam=_display_date(schedule.get("exam_date")),
                result=_display_date(schedule.get("result_date")),
            )
        )
    return lines


def _format_schedule(
    certificate: dict[str, Any], payload: dict[str, Any], year: int
) -> str:
    schedules = [
        schedule
        for schedule in certificate.get("exams", [])
        if int(schedule.get("year") or 0) == year
    ]
    schedules.sort(
        key=lambda schedule: (
            schedule.get("exam_date") or "9999-12-31",
            schedule.get("round") or "",
        )
    )

    source_url = certificate.get("source_url", "")
    source_link = (
        f"[{certificate.get('source_name', '공식 사이트')}]({source_url})"
        if source_url
        else certificate.get("source_name", "공식 사이트")
    )
    last_updated = payload.get("last_updated") or certificate.get("last_updated")
    if last_updated:
        try:
            updated_text = datetime.fromisoformat(last_updated).strftime("%Y.%m.%d %H:%M")
        except ValueError:
            updated_text = str(last_updated)
    else:
        updated_text = "확인되지 않음"

    if not schedules:
        return "\n".join(
            [
                f"## {certificate['certificate_name']} {year}년 시험 일정",
                "",
                "현재 저장된 데이터에서 시험 일정을 확인할 수 없습니다.",
                "공식 사이트에서 최신 일정을 확인해 주세요.",
                "",
                f"- **시행기관:** {certificate.get('source_name', '확인 필요')}",
                f"- **공식 출처:** {source_link}",
                f"- **데이터 기준:** {updated_text}",
            ]
        )

    upcoming = [
        schedule
        for schedule in schedules
        if _schedule_status(schedule) in {"접수 중", "예정", "일정 미정"}
    ]
    completed = [
        schedule for schedule in schedules if _schedule_status(schedule) == "종료"
    ]
    lines = [f"## {certificate['certificate_name']} {year}년 시험 일정", ""]

    if upcoming:
        lines.extend(["### 예정된 시험", "", *_schedule_table(upcoming), ""])
    else:
        lines.extend(["### 예정된 시험", "", "현재 저장된 예정 시험이 없습니다.", ""])

    if completed:
        lines.extend(["### 종료된 시험", "", *_schedule_table(completed), ""])

    lines.extend(
        [
            f"- **데이터 기준:** {updated_text}",
            f"- **시행기관:** {certificate.get('source_name', '확인 필요')}",
            f"- **공식 출처:** {source_link}",
            "",
            "> 시험 일정은 변경될 수 있으므로 접수 전 공식 사이트에서 다시 확인해 주세요.",
        ]
    )
    return "\n".join(lines)


def _format_category_list(
    category: str, certificates: list[dict[str, Any]]
) -> str:
    if category == "디지털":
        filtered = [
            certificate
            for certificate in certificates
            if certificate.get("category") in {"디지털", "IT", "데이터"}
        ]
    else:
        filtered = [
            certificate
            for certificate in certificates
            if certificate.get("category") == category
        ]
    if not filtered:
        return f"현재 저장된 데이터에 **{category}** 분야 자격증이 없습니다."

    lines = [f"## {category} 분야 지원 자격증", ""]
    for certificate in sorted(filtered, key=lambda item: item["certificate_name"]):
        lines.append(
            f"- **{certificate['certificate_name']}** — {certificate.get('description', '')}"
        )
    lines.append("\n자격증명을 입력하면 올해 시험 일정을 알려드릴게요.")
    return "\n".join(lines)


def run(profile: UserProfile, user_input: str) -> str:
    """프로필과 사용자 질문을 받아 자격증 추천 또는 일정 문자열을 반환한다."""
    payload = _load_certificates()
    certificates = payload.get("certificates", [])
    if not certificates:
        return (
            "자격증 데이터 파일을 불러오지 못했습니다. "
            "관리자에게 `data/raw/certs.json`을 확인해 달라고 요청해 주세요."
        )

    user_input = str(user_input or "").strip()
    if not user_input:
        return (
            "어떤 직무로 취업을 준비하고 있나요?\n"
            "예: 은행·금융영업, 증권·자산운용, 데이터 분석, 금융 IT, 백엔드 개발"
        )

    certificate = _find_certificate(user_input, certificates)
    if certificate and _has_any(user_input, SCHEDULE_WORDS):
        return _format_schedule(certificate, payload, date.today().year)

    if _has_any(user_input, SCHEDULE_WORDS):
        referenced_schedule = _resolve_recommended_schedule_request(
            profile, user_input, certificates, payload
        )
        if referenced_schedule:
            return referenced_schedule

    category = _selected_category(user_input)
    if category and _has_any(user_input, LIST_WORDS):
        return _format_category_list(category, certificates)

    is_more = _has_any(user_input, MORE_WORDS)
    exclude = _already_recommended(profile) if is_more else set()
    recommendations = _score_certificates(
        profile=profile,
        user_input=user_input,
        certificates=certificates,
        exclude=exclude,
    )
    _remember(
        profile,
        [certificate["certificate_id"] for certificate in recommendations],
        reset=not is_more,
    )
    return _format_recommendations(recommendations, profile, is_more)
