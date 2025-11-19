from collections.abc import Iterable

from sqlalchemy import select

from ..models import Prompt
from .base import BaseRepository


class PromptRepository(BaseRepository[Prompt]):
    model = Prompt

    async def get_by_name(self, name: str) -> Prompt | None:
        result = await self.session.execute(select(Prompt).where(Prompt.name == name))
        return result.scalars().first()

    async def list_all(self) -> Iterable[Prompt]:
        result = await self.session.execute(select(Prompt).order_by(Prompt.name))
        return result.scalars().all()
