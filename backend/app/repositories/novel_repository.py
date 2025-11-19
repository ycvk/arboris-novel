from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models import Chapter, NovelProject
from .base import BaseRepository


class NovelRepository(BaseRepository[NovelProject]):
    model = NovelProject

    async def get_by_id(self, project_id: str) -> NovelProject | None:
        stmt = (
            select(NovelProject)
            .where(NovelProject.id == project_id)
            .options(
                selectinload(NovelProject.blueprint),
                selectinload(NovelProject.characters),
                selectinload(NovelProject.relationships_),
                selectinload(NovelProject.conversations),
                selectinload(NovelProject.chapters).selectinload(Chapter.versions),
                selectinload(NovelProject.chapters).selectinload(Chapter.evaluations),
                selectinload(NovelProject.chapters).selectinload(
                    Chapter.selected_version
                ),
                selectinload(NovelProject.chapters).selectinload(
                    Chapter.event
                ),  # 预加载事件关系
                # 预加载三层蓝图架构的关联对象，避免 lazy loading 触发 MissingGreenlet 错误
                selectinload(NovelProject.story_framework),
                selectinload(NovelProject.volume_outlines),
                selectinload(NovelProject.plot_events),  # 预加载情节事件（第三层蓝图）
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_user(self, user_id: int) -> Iterable[NovelProject]:
        result = await self.session.execute(
            select(NovelProject)
            .where(NovelProject.user_id == user_id)
            .order_by(NovelProject.updated_at.desc())
            .options(
                selectinload(NovelProject.blueprint),
                selectinload(NovelProject.chapters).selectinload(
                    Chapter.selected_version
                ),
                selectinload(NovelProject.chapters).selectinload(
                    Chapter.event
                ),  # 预加载事件关系
                # 预加载三层蓝图架构的关联对象
                selectinload(NovelProject.story_framework),
                selectinload(NovelProject.volume_outlines),
                selectinload(NovelProject.plot_events),  # 预加载情节事件（第三层蓝图）
            )
        )
        return result.scalars().all()

    async def list_all(self) -> Iterable[NovelProject]:
        result = await self.session.execute(
            select(NovelProject)
            .order_by(NovelProject.updated_at.desc())
            .options(
                selectinload(NovelProject.owner),
                selectinload(NovelProject.blueprint),
                selectinload(NovelProject.chapters).selectinload(
                    Chapter.selected_version
                ),
                selectinload(NovelProject.chapters).selectinload(
                    Chapter.event
                ),  # 预加载事件关系
                # 预加载三层蓝图架构的关联对象
                selectinload(NovelProject.story_framework),
                selectinload(NovelProject.volume_outlines),
                selectinload(NovelProject.plot_events),  # 预加载情节事件（第三层蓝图）
            )
        )
        return result.scalars().all()
