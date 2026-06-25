from core.schema import UserProfile
from app.main import _contextualize_message, enter_chat


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


def test_contextualizer_falls_back_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    message = "그거 일정 알려줘"
    assert (
        _contextualize_message(
            message,
            [{"role": "assistant", "content": "SQLD를 추천했어요."}],
            UserProfile(),
            "certificate",
        )
        == message
    )
