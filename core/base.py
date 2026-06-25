from typing import Protocol

from core.schema import UserProfile


class Tool(Protocol):
    name: str

    def run(self, profile: UserProfile, user_input: str) -> str: ...
