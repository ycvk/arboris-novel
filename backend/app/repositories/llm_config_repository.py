from sqlalchemy import select

from ..models import LLMConfig
from .base import BaseRepository


class LLMConfigRepository(BaseRepository[LLMConfig]):
    model = LLMConfig

    async def get_by_user(self, user_id: int) -> LLMConfig | None:
        result = await self.session.execute(
            select(LLMConfig).where(LLMConfig.user_id == user_id)
        )
        return result.scalars().first()
