from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    # session_id: 사용자(브라우저 세션)별 고유 ID. app/main.py가 Gradio
    # 세션 해시를 주입한다. Tool이 사용자별 상태(추천 이력 등)를 들고 있다면
    # 반드시 이 값으로 키를 잡아야 한다. 프로필 내용으로 키를 잡으면 동일 프로필
    # 입력 사용자끼리 상태가 충돌한다. (계약 상세: README.md / AGENTS.md)
    session_id: str = ""
    education: str = ""
    target_job: str = ""
    skills: list[str] = Field(default_factory=list)
    experiences: list[str] = Field(default_factory=list)
    certs: list[str] = Field(default_factory=list)
