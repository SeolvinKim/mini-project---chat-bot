from core.schema import UserProfile
from app.main import _route_message, enter_chat


def test_user_profile_defaults_are_independent() -> None:
    first = UserProfile()
    second = UserProfile()
    first.skills.append("Python")
    assert second.skills == []


def test_can_enter_without_target_job() -> None:
    profile, _, _, summary, error = enter_chat("", "", "", "", "")
    assert profile["target_job"] == ""
    assert "희망 직무 미정" in summary
    assert error == ""


def test_router_uses_keywords_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    decision = _route_message(
        "SQLD 시험 일정 알려줘",
        [],
        UserProfile(),
    )
    assert decision.tool == "certificate"
    assert decision.standalone_query == "SQLD 시험 일정 알려줘"


def test_router_keeps_previous_tool_for_follow_up_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    decision = _route_message(
        "그거 더 자세히 알려줘",
        [{"role": "assistant", "content": "자격증 세 개를 추천했어요."}],
        UserProfile(),
        "certificate",
    )
    assert decision.tool == "certificate"
