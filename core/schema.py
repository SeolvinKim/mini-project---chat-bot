from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    education: str = ""
    target_job: str = ""
    skills: list[str] = Field(default_factory=list)
    experiences: list[str] = Field(default_factory=list)
    certs: list[str] = Field(default_factory=list)
