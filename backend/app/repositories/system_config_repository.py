from collections.abc import Iterable

from sqlalchemy import select

from ..models import SystemConfig
from .base import BaseRepository


class SystemConfigRepository(BaseRepository[SystemConfig]):
    model = SystemConfig

    async def get_by_key(self, key: str) -> SystemConfig | None:
        result = await self.session.execute(
            select(SystemConfig).where(SystemConfig.key == key)
        )
        return result.scalars().first()

    async def list_all(self) -> Iterable[SystemConfig]:
        result = await self.session.execute(
            select(SystemConfig).order_by(SystemConfig.key)
        )
        return result.scalars().all()
