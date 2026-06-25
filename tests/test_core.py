from core.schema import UserProfile
from app.main import DEFAULT_TOOL, TOOL_MAP, enter_chat, respond, select_tool


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


def test_select_tool_switches_active_tool_and_button_variants() -> None:
    active_tool, _, _, _, *button_updates = select_tool("certificate")
    assert active_tool == "certificate"
    certificate_index = list(TOOL_MAP).index("certificate")
    assert button_updates[certificate_index]["variant"] == "primary"
    assert all(
        update["variant"] == "secondary"
        for index, update in enumerate(button_updates)
        if index != certificate_index
    )


def test_respond_uses_active_tool_not_message_keywords() -> None:
    # active_tool="job"이면 메시지에 "자격증" 키워드가 있어도 job Tool로 응답해야 한다.
    # 빈 프로필 + 짧은 입력이므로 job Tool은 추가 정보 요청 안내를 반환한다 —
    # 메시지 내용으로 자동으로 certificate Tool로 전환(=락인 버그의 반대 증상)되면 안 된다.
    _, history, _ = respond("자격증 추천해줘", None, {}, "job")
    answer = history[-1]["content"]
    assert "정보가 조금 부족" in answer
    # certificate Tool의 일정/추천 결과(시험 일정·자격증명 안내)가 섞이면 안 된다.
    assert "시험 일정" not in answer


def test_default_tool_is_first_tool() -> None:
    assert DEFAULT_TOOL == "job"
