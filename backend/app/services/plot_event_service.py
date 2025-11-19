"""情节事件服务.

提供情节事件的 CRUD 操作、进度追踪、关键点验证等功能。
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ..models.novel import PlotEvent, StoryFramework, VolumeOutline
from ..schemas.plot_event import PlotEventCreate, PlotEventUpdate
from ..services.llm_service import LLMService

logger = logging.getLogger(__name__)


class PlotEventService:
    """情节事件服务."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm_service = LLMService(session)

    # ==================== CRUD 操作 ====================

    async def create_event(
        self, project_id: str, volume_id: int, event_data: PlotEventCreate
    ) -> PlotEvent:
        """创建情节事件."""
        event = PlotEvent(
            project_id=project_id,
            volume_id=volume_id,
            event_id=event_data.event_id,
            event_title=event_data.event_title,
            act=event_data.act,
            arc_index=event_data.arc_index,
            event_type=event_data.event_type,
            description=event_data.description,
            estimated_chapters=event_data.estimated_chapters,
            key_points=event_data.key_points,
            completed_key_points=[],
            pacing=event_data.pacing,
            tension_level=event_data.tension_level,
            sequence=event_data.sequence,
            progress=0,
            status="pending",
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        logger.info(
            "创建情节事件成功",
            extra={"project_id": project_id, "event_id": event_data.event_id},
        )
        return event

    async def get_event_by_id(self, event_id: int) -> PlotEvent | None:
        """根据ID获取事件."""
        return await self.session.get(PlotEvent, event_id)

    async def get_events_by_volume(self, volume_id: int) -> list[PlotEvent]:
        """获取指定卷的所有事件."""
        stmt = (
            select(PlotEvent)
            .where(PlotEvent.volume_id == volume_id)
            .order_by(PlotEvent.sequence)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_events_by_project(self, project_id: str) -> list[PlotEvent]:
        """获取指定项目的所有事件."""
        stmt = (
            select(PlotEvent)
            .where(PlotEvent.project_id == project_id)
            .order_by(PlotEvent.sequence)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_event(
        self, event_id: int, event_data: PlotEventUpdate
    ) -> PlotEvent | None:
        """更新事件."""
        event = await self.get_event_by_id(event_id)
        if not event:
            return None

        update_data = event_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(event, key, value)

        await self.session.commit()
        await self.session.refresh(event)
        logger.info("更新情节事件成功", extra={"event_id": event_id})
        return event

    async def delete_event(self, event_id: int) -> bool:
        """删除事件."""
        event = await self.get_event_by_id(event_id)
        if not event:
            return False

        await self.session.delete(event)
        await self.session.commit()
        logger.info("删除情节事件成功", extra={"event_id": event_id})
        return True

    # ==================== 事件进度追踪 ====================

    async def get_current_event(
        self, project_id: str, volume_id: int
    ) -> PlotEvent | None:
        """获取当前正在进行的事件（预加载 volume 关系）."""
        stmt = (
            select(PlotEvent)
            .options(joinedload(PlotEvent.volume))  # 预加载 volume 关系
            .where(PlotEvent.project_id == project_id)
            .where(PlotEvent.volume_id == volume_id)
            .where(PlotEvent.status.in_(["pending", "in_progress"]))
            .order_by(PlotEvent.sequence)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def update_event_progress(
        self,
        event_id: int,
        progress: int,
        completed_key_points: list[str] | None = None,
    ) -> PlotEvent | None:
        """更新事件进度."""
        event = await self.get_event_by_id(event_id)
        if not event:
            return None

        event.progress = progress

        if completed_key_points is not None:
            event.completed_key_points = completed_key_points

        # 根据进度更新状态
        if progress == 0:
            event.status = "pending"
        elif progress >= 100:
            event.status = "completed"
        else:
            event.status = "in_progress"

        await self.session.commit()
        await self.session.refresh(event)
        logger.info(
            "更新事件进度成功", extra={"event_id": event_id, "progress": progress}
        )
        return event

    async def mark_event_complete(self, event_id: int) -> PlotEvent | None:
        """标记事件为完成."""
        return await self.update_event_progress(event_id, 100)

    async def validate_key_points_completion(self, event_id: int) -> dict[str, Any]:
        """验证事件的关键点是否全部完成."""
        event = await self.get_event_by_id(event_id)
        if not event:
            return {"valid": False, "error": "事件不存在"}

        key_points = event.key_points or []
        completed_key_points = event.completed_key_points or []

        # 检查所有关键点是否都已完成
        all_completed = all(kp in completed_key_points for kp in key_points)

        return {
            "valid": all_completed,
            "total_key_points": len(key_points),
            "completed_key_points": len(completed_key_points),
            "remaining_key_points": [
                kp for kp in key_points if kp not in completed_key_points
            ],
            "completion_rate": len(completed_key_points) / len(key_points)
            if key_points
            else 1.0,
        }

    # ==================== 生成事件 ====================

    async def generate_events_for_volume(
        self, project_id: str, volume_id: int, user_id: int
    ) -> list[PlotEvent]:
        """为指定卷生成情节事件（第一卷）.

        Args:
            project_id: 项目ID
            volume_id: 卷ID
            user_id: 用户ID

        Returns:
            生成的事件列表

        """
        import json

        from ..prompts.blueprint import step6b_plot_events
        from ..utils.json_utils import remove_think_tags

        # 1. 获取卷大纲
        volume = await self.session.get(VolumeOutline, volume_id)
        if not volume:
            raise ValueError(f"卷不存在: {volume_id}")

        volume_outline = {
            "volume_number": volume.volume_number,
            "volume_title": volume.volume_title,
            "volume_goal": volume.volume_goal,
            "estimated_chapters": volume.estimated_chapters,
            "major_arcs": volume.major_arcs,
        }

        # 2. 获取三幕式结构
        framework = await self.session.get(StoryFramework, project_id)
        if not framework:
            raise ValueError(f"三幕式结构不存在: {project_id}")

        overall_arc = framework.overall_arc

        # 3. 获取项目基本信息
        from ..models.novel import NovelProject

        project = await self.session.get(NovelProject, project_id)
        if not project or not project.blueprint:
            raise ValueError(f"项目或蓝图不存在: {project_id}")

        title = project.blueprint.title or ""
        genre = project.blueprint.genre or ""
        tone = project.blueprint.tone or ""

        # 4. 调用 Prompt 生成事件
        system_prompt, user_prompt = step6b_plot_events.build_prompt(
            title=title,
            genre=genre,
            tone=tone,
            overall_arc=overall_arc,
            volume_outline=volume_outline,
            estimated_total_chapters=framework.estimated_total_chapters,
        )

        response = await self.llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=[{"role": "user", "content": user_prompt}],
            user_id=user_id,
        )

        # 5. 解析响应
        response = remove_think_tags(response)
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            # 尝试从 markdown 代码块中提取 JSON
            import re

            match = re.search(r"```json\s*(\{.*\})\s*```", response, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
            else:
                raise ValueError(f"无法解析LLM响应为JSON: {response}")

        plot_events_data = data.get("plot_events", [])
        if not plot_events_data:
            raise ValueError("生成的事件列表为空")

        # 6. 保存事件到数据库
        events = []
        for event_data in plot_events_data:
            event = PlotEvent(
                project_id=project_id,
                volume_id=volume_id,
                event_id=event_data.get("event_id"),
                event_title=event_data.get("event_title"),
                act=event_data.get("act"),
                arc_index=event_data.get("arc_index"),
                event_type=event_data.get("event_type"),
                description=event_data.get("description"),
                estimated_chapters=event_data.get("estimated_chapters"),
                key_points=event_data.get("key_points", []),
                completed_key_points=[],
                pacing=event_data.get("pacing"),
                tension_level=event_data.get("tension_level"),
                sequence=event_data.get("sequence"),
                progress=0,
                status="pending",
            )
            self.session.add(event)
            events.append(event)

        await self.session.commit()

        # 刷新所有事件以获取数据库生成的ID
        for event in events:
            await self.session.refresh(event)

        logger.info(
            "生成事件成功",
            extra={
                "project_id": project_id,
                "volume_id": volume_id,
                "events_count": len(events),
            },
        )

        return events

    async def generate_rolling_events(
        self, project_id: str, current_volume_id: int, next_volume_number: int
    ) -> list[PlotEvent]:
        """滚动生成下一卷的事件.

        Args:
            project_id: 项目ID
            current_volume_id: 当前卷ID
            next_volume_number: 下一卷的卷号

        Returns:
            生成的事件列表

        """
        import json

        from ..prompts.blueprint import generate_rolling_events
        from ..utils.json_utils import remove_think_tags

        # 1. 获取当前卷的所有已完成事件
        completed_events = await self.get_events_by_volume(current_volume_id)
        completed_events_data = [
            {
                "event_id": e.event_id,
                "event_title": e.event_title,
                "act": e.act,
                "arc_index": e.arc_index,
                "event_type": e.event_type,
                "description": e.description,
                "key_points": e.key_points,
                "completed_key_points": e.completed_key_points,
                "pacing": e.pacing,
                "tension_level": e.tension_level,
            }
            for e in completed_events
        ]

        # 2. 获取当前卷的大纲
        current_volume = await self.session.get(VolumeOutline, current_volume_id)
        if not current_volume:
            raise ValueError(f"当前卷不存在: {current_volume_id}")

        current_volume_outline = {
            "volume_number": current_volume.volume_number,
            "volume_title": current_volume.volume_title,
            "volume_goal": current_volume.volume_goal,
            "estimated_chapters": current_volume.estimated_chapters,
            "major_arcs": current_volume.major_arcs,
        }

        # 3. 获取三幕式结构
        framework = await self.session.get(StoryFramework, project_id)
        if not framework:
            raise ValueError(f"三幕式结构不存在: {project_id}")

        overall_arc = framework.overall_arc

        # 4. 获取项目基本信息
        from ..models.novel import NovelProject

        project = await self.session.get(NovelProject, project_id)
        if not project or not project.blueprint:
            raise ValueError(f"项目或蓝图不存在: {project_id}")

        title = project.blueprint.title or ""
        genre = project.blueprint.genre or ""
        tone = project.blueprint.tone or ""

        # 5. 调用 Prompt 生成下一卷的事件
        system_prompt, user_prompt = generate_rolling_events.build_prompt(
            title=title,
            genre=genre,
            tone=tone,
            overall_arc=overall_arc,
            current_volume_outline=current_volume_outline,
            completed_events=completed_events_data,
            previous_volume_number=current_volume.volume_number,
            estimated_total_chapters=framework.estimated_total_chapters,
        )

        response = await self.llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=[{"role": "user", "content": user_prompt}],
        )

        # 6. 解析响应
        response = remove_think_tags(response)
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            # 尝试从 markdown 代码块中提取 JSON
            import re

            match = re.search(r"```json\s*(\{.*\})\s*```", response, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
            else:
                raise ValueError(f"无法解析LLM响应为JSON: {response}")

        plot_events_data = data.get("plot_events", [])
        if not plot_events_data:
            raise ValueError("生成的事件列表为空")

        logger.info(
            "滚动生成事件成功",
            extra={
                "project_id": project_id,
                "next_volume_number": next_volume_number,
                "events_count": len(plot_events_data),
            },
        )

        return plot_events_data
