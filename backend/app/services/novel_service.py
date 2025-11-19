from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_PREFERRED_CONTENT_KEYS: tuple[str, ...] = (
    "content",
    "chapter_content",
    "chapter_text",
    "full_content",
    "text",
    "body",
    "story",
    "chapter",
    "real_summary",
    "summary",
)


def _normalize_version_content(raw_content: Any, metadata: Any) -> str:
    text = _coerce_text(metadata)
    if not text:
        text = _coerce_text(raw_content)
    return text or ""


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _clean_string(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in _PREFERRED_CONTENT_KEYS:
            if key in value and value[key]:
                nested = _coerce_text(value[key])
                if nested:
                    return nested
        return _clean_string(json.dumps(value, ensure_ascii=False))
    if isinstance(value, (list, tuple, set)):
        parts = [text for text in (_coerce_text(item) for item in value) if text]
        if parts:
            return "\n".join(parts)
        return None
    return _clean_string(str(value))


def _clean_string(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return stripped
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed = json.loads(stripped)
            coerced = _coerce_text(parsed)
            if coerced:
                return coerced
        except json.JSONDecodeError:
            pass
    if stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2:
        stripped = stripped[1:-1]
    return (
        stripped.replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )


from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    BlueprintCharacter,
    BlueprintRelationship,
    Chapter,
    ChapterEvaluation,
    ChapterVersion,
    NovelBlueprint,
    NovelConversation,
    NovelProject,
    PlotEvent,
    VolumeOutline,
)
from ..repositories.novel_repository import NovelRepository
from ..schemas.admin import AdminNovelSummary
from ..schemas.novel import (
    Blueprint,
    ChapterGenerationStatus,
    MajorArc,
    NovelProjectSummary,
    NovelSectionResponse,
    NovelSectionType,
    StoryFrameworkSchema,
    VolumeOutlineSchema,
)
from ..schemas.novel import (
    Chapter as ChapterSchema,
)
from ..schemas.novel import (
    NovelProject as NovelProjectSchema,
)


class NovelService:
    """小说项目服务，基于拆表后的结构提供聚合与业务操作。."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = NovelRepository(session)

    # ------------------------------------------------------------------
    # 项目与摘要
    # ------------------------------------------------------------------
    async def create_project(
        self, user_id: int, title: str, initial_prompt: str
    ) -> NovelProject:
        project = NovelProject(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=title,
            initial_prompt=initial_prompt,
        )
        blueprint = NovelBlueprint(project=project)
        self.session.add_all([project, blueprint])
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def ensure_project_owner(self, project_id: str, user_id: int) -> NovelProject:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在"
            )
        if project.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该项目"
            )
        return project

    async def get_project_schema(
        self, project_id: str, user_id: int
    ) -> NovelProjectSchema:
        project = await self.ensure_project_owner(project_id, user_id)
        return await self._serialize_project(project)

    async def get_section_data(
        self,
        project_id: str,
        user_id: int,
        section: NovelSectionType,
    ) -> NovelSectionResponse:
        project = await self.ensure_project_owner(project_id, user_id)
        return self._build_section_response(project, section)

    async def get_chapter_schema(
        self,
        project_id: str,
        user_id: int,
        chapter_number: int,
    ) -> ChapterSchema:
        project = await self.ensure_project_owner(project_id, user_id)
        return self._build_chapter_schema(project, chapter_number)

    async def list_projects_for_user(self, user_id: int) -> list[NovelProjectSummary]:
        projects = await self.repo.list_by_user(user_id)
        summaries: list[NovelProjectSummary] = []
        for project in projects:
            blueprint = project.blueprint
            genre = blueprint.genre if blueprint and blueprint.genre else "未知"
            # 事件驱动模式：直接从 chapters 获取章节信息
            chapters = project.chapters
            total = len(chapters)
            completed = sum(1 for chapter in chapters if chapter.selected_version_id)
            summaries.append(
                NovelProjectSummary(
                    id=project.id,
                    title=project.title,
                    genre=genre,
                    last_edited=project.updated_at.isoformat()
                    if project.updated_at
                    else "未知",
                    completed_chapters=completed,
                    total_chapters=total,
                )
            )
        return summaries

    async def list_projects_for_admin(self) -> list[AdminNovelSummary]:
        projects = await self.repo.list_all()
        summaries: list[AdminNovelSummary] = []
        for project in projects:
            blueprint = project.blueprint
            genre = blueprint.genre if blueprint and blueprint.genre else "未知"
            # 事件驱动模式：直接从 chapters 获取章节信息
            chapters = project.chapters
            total = len(chapters)
            completed = sum(1 for chapter in chapters if chapter.selected_version_id)
            owner = project.owner
            summaries.append(
                AdminNovelSummary(
                    id=project.id,
                    title=project.title,
                    owner_id=owner.id if owner else 0,
                    owner_username=owner.username if owner else "未知",
                    genre=genre,
                    last_edited=project.updated_at.isoformat()
                    if project.updated_at
                    else "",
                    completed_chapters=completed,
                    total_chapters=total,
                )
            )
        return summaries

    async def delete_projects(self, project_ids: list[str], user_id: int) -> None:
        for pid in project_ids:
            project = await self.ensure_project_owner(pid, user_id)
            await self.repo.delete(project)
        await self.session.commit()

    async def count_projects(self) -> int:
        result = await self.session.execute(select(func.count(NovelProject.id)))
        return result.scalar_one()

    # ------------------------------------------------------------------
    # 对话管理
    # ------------------------------------------------------------------
    async def list_conversations(self, project_id: str) -> list[NovelConversation]:
        stmt = (
            select(NovelConversation)
            .where(NovelConversation.project_id == project_id)
            .order_by(NovelConversation.seq.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def append_conversation(
        self, project_id: str, role: str, content: str, metadata: dict | None = None
    ) -> None:
        result = await self.session.execute(
            select(func.max(NovelConversation.seq)).where(
                NovelConversation.project_id == project_id
            )
        )
        current_max = result.scalar()
        next_seq = (current_max or 0) + 1
        convo = NovelConversation(
            project_id=project_id,
            seq=next_seq,
            role=role,
            content=content,
            metadata=metadata,
        )
        self.session.add(convo)
        await self.session.commit()
        await self._touch_project(project_id)

    async def pop_last_conversation(
        self, project_id: str, role: str | None = None
    ) -> bool:
        """删除最后一条对话记录（可选按角色过滤）。返回是否删除成功。."""
        stmt = (
            select(NovelConversation)
            .where(NovelConversation.project_id == project_id)
            .order_by(NovelConversation.seq.desc())
        )
        result = await self.session.execute(stmt)
        for convo in result.scalars():
            if role is None or (convo.role == role):
                await self.session.delete(convo)
                await self.session.commit()
                await self._touch_project(project_id)
                return True
        return False

    # ------------------------------------------------------------------
    # 蓝图管理
    # ------------------------------------------------------------------
    async def replace_blueprint(self, project_id: str, blueprint: Blueprint) -> None:
        from ..models.novel import PlotEvent, StoryFramework, VolumeOutline

        # 调试日志：检查接收到的蓝图数据
        logger.info(
            f"保存蓝图 - project_id={project_id}",
            extra={
                "has_story_framework": blueprint.story_framework is not None,
                "has_volume_outlines": len(blueprint.volume_outlines) > 0,
                "has_stage4_data": blueprint.stage4_data is not None,
                "story_framework": blueprint.story_framework.model_dump()
                if blueprint.story_framework
                else None,
                "volume_outlines_count": len(blueprint.volume_outlines),
                "plot_events_count": len(blueprint.stage4_data.plot_events)
                if blueprint.stage4_data
                else 0,
            },
        )

        record = await self.session.get(NovelBlueprint, project_id)
        if not record:
            record = NovelBlueprint(project_id=project_id)
            self.session.add(record)
        record.title = blueprint.title
        record.target_audience = blueprint.target_audience
        record.genre = blueprint.genre
        record.style = blueprint.style
        record.tone = blueprint.tone
        record.one_sentence_summary = blueprint.one_sentence_summary
        record.full_synopsis = blueprint.full_synopsis
        record.world_setting = blueprint.world_setting

        await self.session.execute(
            delete(BlueprintCharacter).where(
                BlueprintCharacter.project_id == project_id
            )
        )
        for index, data in enumerate(blueprint.characters):
            self.session.add(
                BlueprintCharacter(
                    project_id=project_id,
                    name=data.get("name", ""),
                    identity=data.get("identity"),
                    personality=data.get("personality"),
                    goals=data.get("goals"),
                    abilities=data.get("abilities"),
                    relationship_to_protagonist=data.get("relationship_to_protagonist"),
                    extra={
                        k: v
                        for k, v in data.items()
                        if k
                        not in {
                            "name",
                            "identity",
                            "personality",
                            "goals",
                            "abilities",
                            "relationship_to_protagonist",
                        }
                    },
                    position=index,
                )
            )

        await self.session.execute(
            delete(BlueprintRelationship).where(
                BlueprintRelationship.project_id == project_id
            )
        )
        for index, relation in enumerate(blueprint.relationships):
            self.session.add(
                BlueprintRelationship(
                    project_id=project_id,
                    character_from=relation.character_from,
                    character_to=relation.character_to,
                    description=relation.description,
                    position=index,
                )
            )

        # 新增：保存三层蓝图架构 - StoryFramework
        if blueprint.story_framework:
            logger.info(
                f"保存 StoryFramework - project_id={project_id}",
                extra={
                    "overall_arc": blueprint.story_framework.overall_arc.model_dump(),
                    "estimated_total_chapters": blueprint.story_framework.estimated_total_chapters,
                },
            )
            existing_framework = await self.session.get(StoryFramework, project_id)
            if existing_framework:
                # 更新现有框架
                existing_framework.overall_arc = (
                    blueprint.story_framework.overall_arc.model_dump()
                )
                existing_framework.estimated_total_chapters = (
                    blueprint.story_framework.estimated_total_chapters
                )
                logger.info(f"更新现有 StoryFramework - project_id={project_id}")
            else:
                # 创建新框架
                framework = StoryFramework(
                    project_id=project_id,
                    overall_arc=blueprint.story_framework.overall_arc.model_dump(),
                    estimated_total_chapters=blueprint.story_framework.estimated_total_chapters,
                )
                self.session.add(framework)
                logger.info(f"创建新 StoryFramework - project_id={project_id}")
        else:
            logger.warning(f"未收到 story_framework 数据 - project_id={project_id}")

        # 新增：保存三层蓝图架构 - VolumeOutlines
        if blueprint.volume_outlines:
            # 删除现有的分卷大纲
            await self.session.execute(
                delete(VolumeOutline).where(VolumeOutline.project_id == project_id)
            )

            # 添加新的分卷大纲
            for volume_schema in blueprint.volume_outlines:
                volume = VolumeOutline(
                    project_id=project_id,
                    volume_number=volume_schema.volume_number,
                    volume_title=volume_schema.volume_title,
                    arc_phase=volume_schema.arc_phase,  # 新增：保存 arc_phase
                    volume_goal=volume_schema.volume_goal,
                    estimated_chapters=volume_schema.estimated_chapters,
                    actual_start_chapter=volume_schema.actual_start_chapter,
                    actual_end_chapter=volume_schema.actual_end_chapter,
                    completion_criteria=volume_schema.completion_criteria,
                    major_arcs=[arc.model_dump() for arc in volume_schema.major_arcs]
                    if volume_schema.major_arcs
                    else None,
                    new_characters=volume_schema.new_characters,
                    foreshadowing=volume_schema.foreshadowing,
                    status=volume_schema.status or "draft",
                )
                self.session.add(volume)

            # 刷新以获取 volume_id
            await self.session.flush()

        # ⭐ 新增：保存三层蓝图架构 - PlotEvents（第三层）
        if blueprint.stage4_data and blueprint.stage4_data.plot_events:
            logger.info(
                f"保存 PlotEvents - project_id={project_id}, count={len(blueprint.stage4_data.plot_events)}"
            )

            # 删除现有的情节事件
            await self.session.execute(
                delete(PlotEvent).where(PlotEvent.project_id == project_id)
            )

            # 获取第一卷的 volume_id (蓝图创建时的事件都属于第一卷)
            from sqlalchemy import select

            stmt = select(VolumeOutline).where(
                VolumeOutline.project_id == project_id, VolumeOutline.volume_number == 1
            )
            result = await self.session.execute(stmt)
            first_volume = result.scalar_one_or_none()

            if not first_volume:
                logger.error(
                    f"未找到第一卷 - project_id={project_id}, 无法保存 plot_events"
                )
                raise ValueError("必须先创建第一卷才能保存情节事件")

            default_volume_id = first_volume.id
            logger.info(f"使用第一卷 volume_id={default_volume_id} 保存情节事件")

            # 添加新的情节事件
            for event_data in blueprint.stage4_data.plot_events:
                event = PlotEvent(
                    project_id=project_id,
                    volume_id=event_data.get("volume_id")
                    or default_volume_id,  # ⭐ 使用第一卷的 ID
                    event_id=event_data.get("event_id"),
                    event_title=event_data.get("event_title", ""),
                    act=event_data.get("act", "act1"),
                    arc_index=event_data.get("arc_index", 0),
                    event_type=event_data.get("event_type", "development"),
                    description=event_data.get("description", ""),
                    estimated_chapters=event_data.get("estimated_chapters", "1"),
                    key_points=event_data.get("key_points", []),
                    completed_key_points=event_data.get("completed_key_points", []),
                    pacing=event_data.get("pacing", "medium"),
                    tension_level=event_data.get("tension_level", "medium"),
                    sequence=event_data.get("sequence", 0),
                    progress=event_data.get("progress", 0),
                    status=event_data.get("status", "pending"),
                )
                self.session.add(event)

            logger.info(
                f"成功保存 {len(blueprint.stage4_data.plot_events)} 个情节事件到第一卷"
            )
        else:
            logger.warning(f"未收到 plot_events 数据 - project_id={project_id}")

        await self.session.commit()
        await self._touch_project(project_id)

    async def patch_blueprint(self, project_id: str, patch: dict) -> None:
        blueprint = await self.session.get(NovelBlueprint, project_id)
        if not blueprint:
            blueprint = NovelBlueprint(project_id=project_id)
            self.session.add(blueprint)

        if "one_sentence_summary" in patch:
            blueprint.one_sentence_summary = patch["one_sentence_summary"]
        if "full_synopsis" in patch:
            blueprint.full_synopsis = patch["full_synopsis"]
        if "world_setting" in patch and patch["world_setting"] is not None:
            # 创建新字典对象以触发 SQLAlchemy 的变更检测
            existing = blueprint.world_setting or {}
            blueprint.world_setting = {**existing, **patch["world_setting"]}
        if "characters" in patch and patch["characters"] is not None:
            await self.session.execute(
                delete(BlueprintCharacter).where(
                    BlueprintCharacter.project_id == project_id
                )
            )
            for index, data in enumerate(patch["characters"]):
                self.session.add(
                    BlueprintCharacter(
                        project_id=project_id,
                        name=data.get("name", ""),
                        identity=data.get("identity"),
                        personality=data.get("personality"),
                        goals=data.get("goals"),
                        abilities=data.get("abilities"),
                        relationship_to_protagonist=data.get(
                            "relationship_to_protagonist"
                        ),
                        extra={
                            k: v
                            for k, v in data.items()
                            if k
                            not in {
                                "name",
                                "identity",
                                "personality",
                                "goals",
                                "abilities",
                                "relationship_to_protagonist",
                            }
                        },
                        position=index,
                    )
                )
        if "relationships" in patch and patch["relationships"] is not None:
            await self.session.execute(
                delete(BlueprintRelationship).where(
                    BlueprintRelationship.project_id == project_id
                )
            )
            for index, relation in enumerate(patch["relationships"]):
                self.session.add(
                    BlueprintRelationship(
                        project_id=project_id,
                        character_from=relation.get("character_from"),
                        character_to=relation.get("character_to"),
                        description=relation.get("description"),
                        position=index,
                    )
                )
        await self.session.commit()
        await self._touch_project(project_id)

    # ------------------------------------------------------------------
    # 章节与版本
    # ------------------------------------------------------------------
    async def get_or_create_chapter(
        self, project_id: str, chapter_number: int
    ) -> Chapter:
        stmt = select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number,
        )
        result = await self.session.execute(stmt)
        chapter = result.scalars().first()
        if chapter:
            return chapter
        chapter = Chapter(project_id=project_id, chapter_number=chapter_number)
        self.session.add(chapter)
        await self.session.commit()
        await self.session.refresh(chapter)
        return chapter

    async def replace_chapter_versions(
        self, chapter: Chapter, contents: list[str], metadata: list[dict] | None = None
    ) -> list[ChapterVersion]:
        await self.session.execute(
            delete(ChapterVersion).where(ChapterVersion.chapter_id == chapter.id)
        )
        versions: list[ChapterVersion] = []
        for index, content in enumerate(contents):
            extra = metadata[index] if metadata and index < len(metadata) else None
            text_content = _normalize_version_content(content, extra)
            version = ChapterVersion(
                chapter_id=chapter.id,
                content=text_content,
                metadata=None,
                version_label=f"v{index + 1}",
            )
            self.session.add(version)
            versions.append(version)

        # 生成多个版本后,不自动选择,让用户自己选择最好的版本
        # 状态设为 waiting_for_confirm,等待用户确认
        if versions:
            chapter.status = ChapterGenerationStatus.WAITING_FOR_CONFIRM.value
            # 不设置 selected_version_id,让用户自己选择
            chapter.selected_version_id = None
            chapter.word_count = 0
        else:
            chapter.status = ChapterGenerationStatus.WAITING_FOR_CONFIRM.value

        await self.session.commit()
        await self.session.refresh(chapter)
        await self._touch_project(chapter.project_id)
        return versions

    async def select_chapter_version(
        self, chapter: Chapter, version_index: int
    ) -> ChapterVersion:
        versions = sorted(chapter.versions, key=lambda item: item.created_at)
        if not versions or version_index < 0 or version_index >= len(versions):
            raise HTTPException(status_code=400, detail="版本索引无效")
        selected = versions[version_index]
        chapter.selected_version_id = selected.id
        chapter.status = ChapterGenerationStatus.SUCCESSFUL.value
        chapter.word_count = len(selected.content or "")
        await self.session.commit()
        await self.session.refresh(chapter)
        await self._touch_project(chapter.project_id)
        return selected

    async def add_chapter_evaluation(
        self,
        chapter: Chapter,
        version: ChapterVersion | None,
        feedback: str,
        decision: str | None = None,
    ) -> None:
        evaluation = ChapterEvaluation(
            chapter_id=chapter.id,
            version_id=version.id if version else None,
            feedback=feedback,
            decision=decision,
        )
        self.session.add(evaluation)
        chapter.status = ChapterGenerationStatus.WAITING_FOR_CONFIRM.value
        await self.session.commit()
        await self.session.refresh(chapter)
        await self._touch_project(chapter.project_id)

    async def delete_chapters(
        self, project_id: str, chapter_numbers: Iterable[int]
    ) -> None:
        await self.session.execute(
            delete(Chapter).where(
                Chapter.project_id == project_id,
                Chapter.chapter_number.in_(list(chapter_numbers)),
            )
        )
        await self.session.commit()
        await self._touch_project(project_id)

    # ------------------------------------------------------------------
    # 事件驱动模式支持
    # ------------------------------------------------------------------
    async def get_current_event_for_chapter(
        self, project_id: str, chapter_number: int
    ) -> PlotEvent | None:
        """获取当前章节应该关联的事件.

        逻辑：
        1. 查找当前正在进行的事件（status = 'in_progress' 或 'pending'）
        2. 如果没有正在进行的事件，返回 None
        3. 按照 sequence 排序，返回第一个未完成的事件
        """
        from ..services.plot_event_service import PlotEventService

        # 获取项目的第一个卷（假设当前只支持第一卷）
        stmt = (
            select(VolumeOutline)
            .where(VolumeOutline.project_id == project_id)
            .order_by(VolumeOutline.volume_number)
        )
        result = await self.session.execute(stmt)
        volume = result.scalars().first()

        if not volume:
            logger.warning(f"项目 {project_id} 没有找到分卷大纲")
            return None

        # 获取当前正在进行的事件
        plot_event_service = PlotEventService(self.session)
        current_event = await plot_event_service.get_current_event(
            project_id, volume.id
        )

        return current_event

    async def update_chapter_event_progress(
        self,
        chapter: Chapter,
        event_progress_after: int,
        completed_key_points: list[str],
        is_event_complete: bool,
    ) -> None:
        """更新章节的事件进度.

        Args:
            chapter: 章节对象
            event_progress_after: 事件完成度（0-100）
            completed_key_points: 这一章完成的关键点
            is_event_complete: 事件是否完成

        """
        from ..services.plot_event_service import PlotEventService

        if not chapter.event_id:
            logger.warning(
                f"章节 {chapter.chapter_number} 没有关联事件，无法更新事件进度"
            )
            return

        # 更新章节的事件进度
        chapter.event_progress = event_progress_after

        # 更新事件的进度
        plot_event_service = PlotEventService(self.session)
        event = await plot_event_service.get_event_by_id(chapter.event_id)

        if not event:
            logger.warning(f"事件 {chapter.event_id} 不存在")
            return

        # 合并已完成的关键点（去重）
        existing_completed = set(event.completed_key_points or [])
        new_completed = existing_completed | set(completed_key_points)

        await plot_event_service.update_event_progress(
            event_id=chapter.event_id,
            progress=event_progress_after,
            completed_key_points=list(new_completed),
        )

        logger.info(
            f"更新章节 {chapter.chapter_number} 的事件进度",
            extra={
                "event_id": chapter.event_id,
                "progress": event_progress_after,
                "completed_key_points": list(new_completed),
                "is_complete": is_event_complete,
            },
        )

    async def check_and_switch_event(
        self, project_id: str, current_event_id: int
    ) -> PlotEvent | None:
        """检查当前事件是否完成，如果完成则切换到下一个事件.

        Args:
            project_id: 项目ID
            current_event_id: 当前事件ID

        Returns:
            下一个事件，如果没有则返回 None

        """
        from ..services.plot_event_service import PlotEventService

        plot_event_service = PlotEventService(self.session)

        # 获取当前事件
        current_event = await plot_event_service.get_event_by_id(current_event_id)
        if not current_event:
            logger.warning(f"事件 {current_event_id} 不存在")
            return None

        # 检查事件是否完成
        if current_event.status != "completed":
            logger.info(f"事件 {current_event_id} 尚未完成，无需切换")
            return current_event

        # 获取下一个事件
        stmt = (
            select(PlotEvent)
            .where(PlotEvent.project_id == project_id)
            .where(PlotEvent.volume_id == current_event.volume_id)
            .where(PlotEvent.sequence > current_event.sequence)
            .where(PlotEvent.status == "pending")
            .order_by(PlotEvent.sequence)
        )
        result = await self.session.execute(stmt)
        next_event = result.scalars().first()

        if next_event:
            # 将下一个事件标记为 in_progress（使用进度1而不是0，因为0会被设置为pending）
            await plot_event_service.update_event_progress(next_event.id, 1)
            logger.info(
                "事件切换成功",
                extra={
                    "from_event": current_event.event_id,
                    "to_event": next_event.event_id,
                    "volume_id": current_event.volume_id,
                },
            )
        else:
            logger.info("当前卷的所有事件已完成，无下一个事件")

        return next_event

    # ------------------------------------------------------------------
    # 序列化辅助
    # ------------------------------------------------------------------
    async def get_project_schema_for_admin(self, project_id: str) -> NovelProjectSchema:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在"
            )
        return await self._serialize_project(project)

    async def get_section_data_for_admin(
        self,
        project_id: str,
        section: NovelSectionType,
    ) -> NovelSectionResponse:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在"
            )
        return self._build_section_response(project, section)

    async def get_chapter_schema_for_admin(
        self,
        project_id: str,
        chapter_number: int,
    ) -> ChapterSchema:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在"
            )
        return self._build_chapter_schema(project, chapter_number)

    async def _serialize_project(self, project: NovelProject) -> NovelProjectSchema:
        # 注：story_framework 和 volume_outlines 已在 repository 中通过 selectinload 预加载
        conversations = [
            {"role": convo.role, "content": convo.content}
            for convo in sorted(project.conversations, key=lambda c: c.seq)
        ]

        blueprint_schema = self._build_blueprint_schema(project)

        # 事件驱动模式：直接从 chapters 获取章节信息，不再使用 outlines
        chapters_map = {chapter.chapter_number: chapter for chapter in project.chapters}
        chapter_numbers = sorted(chapters_map.keys())
        chapters_schema: list[ChapterSchema] = [
            self._build_chapter_schema(
                project,
                number,
                chapters_map=chapters_map,
            )
            for number in chapter_numbers
        ]

        return NovelProjectSchema(
            id=project.id,
            user_id=project.user_id,
            title=project.title,
            initial_prompt=project.initial_prompt or "",
            conversation_history=conversations,
            blueprint=blueprint_schema,
            chapters=chapters_schema,
        )

    async def _touch_project(self, project_id: str) -> None:
        await self.session.execute(
            update(NovelProject)
            .where(NovelProject.id == project_id)
            .values(updated_at=datetime.now(UTC))
        )
        await self.session.commit()

    def _build_blueprint_schema(self, project: NovelProject) -> Blueprint:
        blueprint_obj = project.blueprint

        # 构建 story_framework
        story_framework_schema = None
        if project.story_framework:
            sf = project.story_framework
            story_framework_schema = StoryFrameworkSchema(
                id=sf.id,
                project_id=sf.project_id,
                estimated_total_chapters=sf.estimated_total_chapters,
                overall_arc=sf.overall_arc or {},
                created_at=sf.created_at.isoformat() if sf.created_at else None,
                updated_at=sf.updated_at.isoformat() if sf.updated_at else None,
            )

        # 构建 volume_outlines
        volume_outlines_schemas = []
        for vol in sorted(project.volume_outlines, key=lambda v: v.volume_number):
            volume_outlines_schemas.append(
                VolumeOutlineSchema(
                    id=vol.id,
                    project_id=vol.project_id,
                    volume_number=vol.volume_number,
                    volume_title=vol.volume_title,
                    arc_phase=vol.arc_phase,  # 新增：包含 arc_phase
                    volume_goal=vol.volume_goal,
                    estimated_chapters=vol.estimated_chapters,
                    actual_start_chapter=vol.actual_start_chapter,
                    actual_end_chapter=vol.actual_end_chapter,
                    completion_criteria=vol.completion_criteria or [],
                    major_arcs=[MajorArc(**arc) for arc in (vol.major_arcs or [])]
                    if vol.major_arcs
                    else [],
                    new_characters=vol.new_characters or [],
                    foreshadowing=vol.foreshadowing or [],
                    status=vol.status,
                    created_at=vol.created_at.isoformat() if vol.created_at else None,
                    updated_at=vol.updated_at.isoformat() if vol.updated_at else None,
                )
            )

        # ⭐ 构建 stage4_data（情节事件列表）
        plot_events_data = [
            {
                "id": event.id,
                "volume_id": event.volume_id,
                "event_id": event.event_id,
                "event_title": event.event_title,
                "act": event.act,
                "arc_index": event.arc_index,
                "event_type": event.event_type,
                "description": event.description,
                "estimated_chapters": event.estimated_chapters,
                "key_points": event.key_points or [],
                "completed_key_points": event.completed_key_points or [],
                "pacing": event.pacing,
                "tension_level": event.tension_level,
                "sequence": event.sequence,
                "progress": event.progress,
                "status": event.status,
                "created_at": event.created_at.isoformat()
                if event.created_at
                else None,
                "updated_at": event.updated_at.isoformat()
                if event.updated_at
                else None,
            }
            for event in sorted(project.plot_events, key=lambda e: e.sequence)
        ]

        from app.schemas.novel import Stage4Data

        stage4_data = Stage4Data(plot_events=plot_events_data)

        if blueprint_obj:
            return Blueprint(
                title=blueprint_obj.title or "",
                target_audience=blueprint_obj.target_audience or "",
                genre=blueprint_obj.genre or "",
                style=blueprint_obj.style or "",
                tone=blueprint_obj.tone or "",
                one_sentence_summary=blueprint_obj.one_sentence_summary or "",
                full_synopsis=blueprint_obj.full_synopsis or "",
                world_setting=blueprint_obj.world_setting or {},
                characters=[
                    {
                        "name": character.name,
                        "identity": character.identity,
                        "personality": character.personality,
                        "goals": character.goals,
                        "abilities": character.abilities,
                        "relationship_to_protagonist": character.relationship_to_protagonist,
                        **(character.extra or {}),
                    }
                    for character in sorted(
                        project.characters, key=lambda c: c.position
                    )
                ],
                relationships=[
                    {
                        "character_from": relation.character_from,
                        "character_to": relation.character_to,
                        "description": relation.description or "",
                        "relationship_type": getattr(
                            relation, "relationship_type", None
                        ),
                    }
                    for relation in sorted(
                        project.relationships_, key=lambda r: r.position
                    )
                ],
                # 三层蓝图架构
                story_framework=story_framework_schema,
                volume_outlines=volume_outlines_schemas,
                # ⭐ 新增：阶段4数据（情节事件）
                stage4_data=stage4_data,
            )
        return Blueprint(
            title="",
            target_audience="",
            genre="",
            style="",
            tone="",
            one_sentence_summary="",
            full_synopsis="",
            world_setting={},
            characters=[],
            relationships=[],
            story_framework=story_framework_schema,
            volume_outlines=volume_outlines_schemas,
            stage4_data=stage4_data,
        )

    def _build_section_response(
        self,
        project: NovelProject,
        section: NovelSectionType,
    ) -> NovelSectionResponse:
        blueprint = self._build_blueprint_schema(project)

        if section == NovelSectionType.OVERVIEW:
            data = {
                "title": project.title,
                "initial_prompt": project.initial_prompt or "",
                "status": project.status,
                "one_sentence_summary": blueprint.one_sentence_summary,
                "target_audience": blueprint.target_audience,
                "genre": blueprint.genre,
                "style": blueprint.style,
                "tone": blueprint.tone,
                "full_synopsis": blueprint.full_synopsis,
                "updated_at": project.updated_at.isoformat()
                if project.updated_at
                else None,
            }
        elif section == NovelSectionType.WORLD_SETTING:
            data = {
                "world_setting": blueprint.world_setting or {},
            }
        elif section == NovelSectionType.CHARACTERS:
            data = {
                "characters": blueprint.characters,
            }
        elif section == NovelSectionType.RELATIONSHIPS:
            data = {
                "relationships": blueprint.relationships,
            }
        elif section == NovelSectionType.CHAPTERS:
            # 事件驱动模式：返回已生成的章节 + 情节事件列表
            chapters_map = {
                chapter.chapter_number: chapter for chapter in project.chapters
            }
            chapter_numbers = sorted(chapters_map.keys())
            # 章节列表只返回元数据，不包含完整内容
            chapters = [
                self._build_chapter_schema(
                    project,
                    number,
                    chapters_map=chapters_map,
                    include_content=False,
                ).model_dump()
                for number in chapter_numbers
            ]

            # ⭐ 新增：返回情节事件列表，供左侧边栏显示
            plot_events = [
                {
                    "id": event.id,
                    "volume_id": event.volume_id,
                    "event_id": event.event_id,
                    "event_title": event.event_title,
                    "act": event.act,
                    "arc_index": event.arc_index,
                    "event_type": event.event_type,
                    "description": event.description,
                    "estimated_chapters": event.estimated_chapters,
                    "key_points": event.key_points or [],
                    "completed_key_points": event.completed_key_points or [],
                    "pacing": event.pacing,
                    "tension_level": event.tension_level,
                    "sequence": event.sequence,
                    "progress": event.progress,
                    "status": event.status,
                    "created_at": event.created_at.isoformat()
                    if event.created_at
                    else None,
                    "updated_at": event.updated_at.isoformat()
                    if event.updated_at
                    else None,
                }
                for event in project.plot_events
            ]

            data = {
                "chapters": chapters,
                "total": len(chapters),
                "plot_events": plot_events,  # ⭐ 新增：情节事件列表
            }
        elif section == NovelSectionType.VOLUME_MANAGEMENT:
            # 分卷管理：返回总体框架和分卷大纲
            data = {
                "story_framework": blueprint.story_framework.model_dump()
                if blueprint.story_framework
                else None,
                "volume_outlines": [
                    vol.model_dump() for vol in blueprint.volume_outlines
                ],
            }
        elif section == NovelSectionType.THREE_LAYER_BLUEPRINT:
            # 三层蓝图：返回完整的三层架构
            # 注意：第三层是 plot_events（情节事件），不再是 chapter_outline
            data = {
                "story_framework": blueprint.story_framework.model_dump()
                if blueprint.story_framework
                else None,
                "volume_outlines": [
                    vol.model_dump() for vol in blueprint.volume_outlines
                ],
                "plot_events": [
                    {
                        "id": event.id,
                        "volume_id": event.volume_id,
                        "event_id": event.event_id,
                        "event_title": event.event_title,
                        "act": event.act,
                        "arc_index": event.arc_index,
                        "event_type": event.event_type,
                        "description": event.description,
                        "estimated_chapters": event.estimated_chapters,
                        "key_points": event.key_points or [],
                        "completed_key_points": event.completed_key_points or [],
                        "pacing": event.pacing,
                        "tension_level": event.tension_level,
                        "sequence": event.sequence,
                        "progress": event.progress,
                        "status": event.status,
                        "created_at": event.created_at.isoformat()
                        if event.created_at
                        else None,
                        "updated_at": event.updated_at.isoformat()
                        if event.updated_at
                        else None,
                    }
                    for event in project.plot_events
                ],
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="未知的章节类型"
            )

        return NovelSectionResponse(section=section, data=data)

    def _build_chapter_schema(
        self,
        project: NovelProject,
        chapter_number: int,
        *,
        chapters_map: dict[int, Chapter] | None = None,
        include_content: bool = True,
    ) -> ChapterSchema:
        chapters = chapters_map or {
            chapter.chapter_number: chapter for chapter in project.chapters
        }
        chapter = chapters.get(chapter_number)

        if not chapter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="章节不存在"
            )

        # 从关联的 PlotEvent 获取标题和摘要（事件驱动模式）
        title = f"第{chapter_number}章"
        summary = ""
        if chapter.event:
            title = chapter.event.event_title or title
            summary = chapter.event.description or ""

        real_summary = chapter.real_summary if chapter else None
        content = None
        versions: list[str] | None = None
        evaluation_text: str | None = None
        status_value = chapter.status or ChapterGenerationStatus.NOT_GENERATED.value
        word_count = chapter.word_count or 0

        # 只有在 include_content=True 时才包含完整内容
        if include_content:
            if chapter.selected_version:
                content = chapter.selected_version.content
            if chapter.versions:
                versions = [
                    v.content
                    for v in sorted(chapter.versions, key=lambda item: item.created_at)
                ]
            if chapter.evaluations:
                latest = sorted(chapter.evaluations, key=lambda item: item.created_at)[
                    -1
                ]
                evaluation_text = latest.feedback or latest.decision

        return ChapterSchema(
            chapter_number=chapter_number,
            title=title,
            summary=summary,
            real_summary=real_summary,
            content=content,
            versions=versions,
            evaluation=evaluation_text,
            generation_status=ChapterGenerationStatus(status_value),
            word_count=word_count,
        )
