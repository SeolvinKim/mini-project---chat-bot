from core.schema import UserProfile


def test_user_profile_defaults_are_independent() -> None:
    first = UserProfile()
    second = UserProfile()
    first.skills.append("Python")
    assert second.skills == []
