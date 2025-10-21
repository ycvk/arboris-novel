from typing import Iterable, Optional

from sqlalchemy import select

from .base import BaseRepository
from ..models import SystemConfig


class SystemConfigRepository(BaseRepository[SystemConfig]):
    model = SystemConfig

    async def get_by_key(self, key: str) -> Optional[SystemConfig]:
        result = await self.session.execute(select(SystemConfig).where(SystemConfig.key == key))
        return result.scalars().first()

    async def list_all(self) -> Iterable[SystemConfig]:
        result = await self.session.execute(select(SystemConfig).order_by(SystemConfig.key))
        return result.scalars().all()
