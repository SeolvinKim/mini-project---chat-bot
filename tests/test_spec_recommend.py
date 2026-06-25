from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from tools.spec_recommend import NAME, _recent_recommendation_names, run


@dataclass
class DummyProfile:
    session_id: str = "test-session"
    education: str = "컴퓨터공학"
    target_job: str = "데이터 분석가"
    skills: list[str] = field(default_factory=lambda: ["Python", "SQL"])
    experiences: list[str] = field(default_factory=lambda: ["고객 데이터 분석"])
    certs: list[str] = field(default_factory=list)


def test_contract_returns_string() -> None:
    profile = DummyProfile()
    result = run(profile, "자격증 추천해줘")
    assert NAME == "자격증 추천"
    assert isinstance(result, str)
    assert result


def test_recommends_data_certificates() -> None:
    result = run(DummyProfile(), "데이터 분석가에게 필요한 자격증 추천해줘")
    assert any(name in result for name in ("SQL 개발자", "데이터분석 준전문가", "빅데이터분석기사"))


def test_alias_schedule_lookup() -> None:
    result = run(DummyProfile(), "SQLD 올해 시험 일정 알려줘")
    assert "SQL 개발자" in result
    assert "원서접수 기간" in result
    assert "공식 출처" in result


def test_kofia_alias_schedule_lookup() -> None:
    result = run(DummyProfile(target_job="증권 자산운용"), "투운사 시험 일정 알려줘")
    assert "투자자산운용사" in result
    assert "2026년 시험 일정" in result


def test_profile_is_not_mutated() -> None:
    profile = DummyProfile()
    before = repr(profile)
    run(profile, "자격증 추천해줘")
    assert repr(profile) == before


def test_missing_input_asks_for_job() -> None:
    profile = DummyProfile(target_job="", skills=[], experiences=[])
    result = run(profile, "")
    assert "어떤 직무" in result


def test_generic_recommendation_requires_target_job() -> None:
    profile = DummyProfile(
        session_id="missing-target-session",
        target_job="",
        skills=[],
        experiences=[],
    )
    result = run(profile, "자격증 추천해줘")
    assert "희망 직무" in result
    assert "데이터 분석가" in result


def test_job_in_message_can_start_recommendation_without_profile_job() -> None:
    profile = DummyProfile(
        session_id="job-message-session",
        target_job="",
        skills=[],
        experiences=[],
    )
    result = run(profile, "데이터 분석가 자격증 추천해줘")
    assert "SQL 개발자" in result


def test_more_recommendations_avoid_previous_items() -> None:
    profile = DummyProfile(session_id="more-session")
    first = run(profile, "데이터 분석 자격증 추천해줘")
    second = run(profile, "더 추천해줘")
    first_names = {
        name
        for name in ("SQL 개발자", "데이터분석 준전문가", "빅데이터분석기사")
        if name in first
    }
    assert not all(name in second for name in first_names)


def test_follow_up_schedule_asks_which_recent_recommendation() -> None:
    profile = DummyProfile(session_id="follow-up-session")
    run(profile, "데이터 분석 자격증 추천해줘")
    result = run(profile, "추천해준 자격증 시험 일정 알려줘")
    assert "최근 추천한 자격증이 여러 개" in result
    assert "1번 일정 알려줘" in result


def test_ordinal_follow_up_opens_recent_schedule() -> None:
    profile = DummyProfile(session_id="ordinal-session")
    first = run(profile, "데이터 분석 자격증 추천해줘")
    result = run(profile, "1번 시험 일정 알려줘")
    recommended_names = [
        name
        for name in ("SQL 개발자", "데이터분석 준전문가", "빅데이터분석기사")
        if name in first
    ]
    assert recommended_names
    assert recommended_names[0] in result
    assert "원서접수 기간" in result


def test_bare_number_selects_from_pending_schedule_choices() -> None:
    profile = DummyProfile(session_id="bare-number-session")
    first = run(profile, "데이터 분석 자격증 추천해줘")
    run(profile, "그 자격증 시험 일정 알려줘")
    result = run(profile, "3")
    recommended_names = [
        name
        for name in ("SQL 개발자", "데이터분석 준전문가", "빅데이터분석기사")
        if name in first
    ]
    assert len(recommended_names) == 3
    assert recommended_names[2] in result
    assert "시험 일정" in result


def test_bare_certificate_name_selects_from_pending_choices() -> None:
    profile = DummyProfile(session_id="bare-name-session")
    first = run(profile, "데이터 분석 자격증 추천해줘")
    run(profile, "추천한 자격증 일정 알려줘")
    selected_name = next(
        name
        for name in ("SQL 개발자", "데이터분석 준전문가", "빅데이터분석기사")
        if name in first
    )
    result = run(profile, selected_name)
    assert selected_name in result
    assert "시험 일정" in result


def test_that_certificate_uses_last_focused_certificate() -> None:
    profile = DummyProfile(session_id="focused-certificate-session")
    run(profile, "SQLD 시험 일정 알려줘")
    result = run(profile, "그 자격증 시험 일정 다시 알려줘")
    assert "SQL 개발자" in result
    assert "시험 일정" in result


def test_invalid_bare_number_keeps_pending_context() -> None:
    profile = DummyProfile(session_id="invalid-number-session")
    run(profile, "데이터 분석 자격증 추천해줘")
    run(profile, "그 자격증 시험 일정 알려줘")
    invalid = run(profile, "4")
    valid = run(profile, "2")
    assert "1번부터 3번" in invalid
    assert "시험 일정" in valid


def test_recent_recommendations_are_available_for_ui() -> None:
    profile = DummyProfile(session_id="ui-selector-session")
    run(profile, "데이터 분석 자격증 추천해줘")
    names = _recent_recommendation_names(profile)
    assert len(names) == 3
    assert "SQL 개발자" in names


def test_common_language_test_aliases_are_supported() -> None:
    profile = DummyProfile(target_job="해외영업")
    assert "OPIc" in run(profile, "오픽 시험 일정 알려줘")
    assert "TOEIC Speaking" in run(profile, "토스 일정 알려줘")
    assert "TOEIC" in run(profile, "토익 일정 알려줘")


def test_language_category_list_contains_major_tests() -> None:
    result = run(DummyProfile(target_job="해외영업"), "어학시험 목록 알려줘")
    for name in ("TOEIC", "OPIc", "JLPT", "HSK", "FLEX"):
        assert name in result


def test_frequent_language_test_shows_official_schedule_guidance() -> None:
    result = run(DummyProfile(target_job="해외영업"), "토플 시험 일정 알려줘")
    assert "TOEFL iBT" in result
    assert "수시" in result
    assert "공식 출처" in result


def test_language_dataset_has_unique_ids_and_official_sources() -> None:
    path = Path(__file__).resolve().parents[1] / "data" / "raw" / "language_tests.json"
    certificates = json.loads(path.read_text(encoding="utf-8"))["certificates"]
    certificate_ids = [item["certificate_id"] for item in certificates]

    assert len(certificates) >= 18
    assert len(certificate_ids) == len(set(certificate_ids))
    assert all(item["category"] == "어학" for item in certificates)
    assert all(str(item["source_url"]).startswith("https://") for item in certificates)
