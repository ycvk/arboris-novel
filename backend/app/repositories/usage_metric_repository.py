from sqlalchemy import select

from ..models import UsageMetric
from .base import BaseRepository


class UsageMetricRepository(BaseRepository[UsageMetric]):
    model = UsageMetric

    async def get_or_create(self, key: str) -> UsageMetric:
        result = await self.session.execute(
            select(UsageMetric).where(UsageMetric.key == key)
        )
        instance = result.scalars().first()
        if instance is None:
            instance = UsageMetric(key=key, value=0)
            self.session.add(instance)
            await self.session.flush()
        return instance
