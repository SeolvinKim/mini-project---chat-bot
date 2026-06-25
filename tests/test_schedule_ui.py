from core.schema import UserProfile
from tools.spec_recommend import run


def test_schedule_uses_responsive_cards_instead_of_markdown_table() -> None:
    answer = run(
        UserProfile(session_id="schedule-ui-test"),
        "SQLD 올해 시험 일정 알려줘",
    )

    assert 'class="schedule-response"' in answer
    assert 'class="exam-card"' in answer
    assert "| 상태 |" not in answer
    assert "<table" not in answer
