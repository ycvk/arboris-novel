from sqlalchemy import select

from ..models import AdminSetting
from .base import BaseRepository


class AdminSettingRepository(BaseRepository[AdminSetting]):
    model = AdminSetting

    async def get_value(self, key: str) -> str | None:
        result = await self.session.execute(
            select(AdminSetting).where(AdminSetting.key == key)
        )
        record = result.scalars().first()
        return record.value if record else None
