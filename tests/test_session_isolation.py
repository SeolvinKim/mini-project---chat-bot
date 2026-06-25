from tools import spec_recommend


def _profile(session_id: str) -> dict[str, str]:
    # 내용은 동일, session_id만 다른 두 사용자
    return {"session_id": session_id, "target_job": "데이터 분석", "skills": "SQL"}


def test_history_isolated_by_session() -> None:
    spec_recommend._RECOMMENDATION_HISTORY.clear()
    user_a = _profile("sess-a")
    user_b = _profile("sess-b")

    spec_recommend._remember(user_a, ["sqld"], reset=True)

    assert spec_recommend._already_recommended(user_a) == {"sqld"}
    # 같은 프로필 내용이라도 세션이 다르면 이력이 새지 않아야 한다
    assert spec_recommend._already_recommended(user_b) == set()


def test_same_session_shares_history() -> None:
    spec_recommend._RECOMMENDATION_HISTORY.clear()
    user = _profile("sess-a")

    spec_recommend._remember(user, ["sqld"], reset=True)
    spec_recommend._remember(_profile("sess-a"), ["adsp"], reset=False)

    assert spec_recommend._already_recommended(user) == {"sqld", "adsp"}
