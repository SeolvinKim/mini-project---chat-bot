from __future__ import annotations

from dataclasses import dataclass, field

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


def test_recent_recommendations_are_available_for_ui() -> None:
    profile = DummyProfile(session_id="ui-selector-session")
    run(profile, "데이터 분석 자격증 추천해줘")
    names = _recent_recommendation_names(profile)
    assert len(names) == 3
    assert "SQL 개발자" in names
