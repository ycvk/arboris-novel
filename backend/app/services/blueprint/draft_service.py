"""
蓝图草稿服务
负责保存和恢复蓝图生成过程中的草稿数据
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import attributes

from ...models.novel import NovelProject
from ...schemas.blueprint_stage import BlueprintDraft, SaveDraftRequest

logger = logging.getLogger(__name__)


class DraftService:
    """蓝图草稿服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_draft(
        self,
        project_id: str,
        draft_data: SaveDraftRequest
    ) -> BlueprintDraft:
        """
        保存蓝图草稿

        Args:
            project_id: 项目ID
            draft_data: 草稿数据

        Returns:
            保存后的草稿对象
        """
        logger.info("保存蓝图草稿", extra={
            "project_id": project_id,
            "current_stage": draft_data.current_stage
        })

        # 查询项目
        result = await self.session.execute(
            select(NovelProject).where(NovelProject.id == project_id)
        )
        project = result.scalar_one_or_none()

        if not project:
            raise ValueError(f"项目不存在: {project_id}")

        # 构建草稿数据
        draft_dict = {
            "blueprint_draft": {
                "current_stage": draft_data.current_stage,
                "stage1": draft_data.stage1.model_dump() if draft_data.stage1 else None,
                "stage2": draft_data.stage2.model_dump() if draft_data.stage2 else None,
                "stage3": draft_data.stage3.model_dump() if draft_data.stage3 else None,
                "stage4": draft_data.stage4.model_dump() if draft_data.stage4 else None,
                "updated_at": datetime.utcnow().isoformat()
            }
        }

        # 保存到 metadata 字段
        if project.metadata:
            project.metadata.update(draft_dict)
        else:
            project.metadata = draft_dict

        # 显式标记 metadata_ 字段已修改（关键！）
        # 因为 metadata 使用了 descriptor，SQLAlchemy 无法自动检测到 JSON 字段的变更
        attributes.flag_modified(project, "metadata_")

        await self.session.commit()
        await self.session.refresh(project)

        logger.info(f"草稿保存成功 - project_id={project_id}, current_stage={draft_data.current_stage}")

        return BlueprintDraft(
            project_id=project_id,
            current_stage=draft_data.current_stage,
            stage1=draft_data.stage1,
            stage2=draft_data.stage2,
            stage3=draft_data.stage3,
            stage4=draft_data.stage4,
            updated_at=draft_dict["blueprint_draft"]["updated_at"]
        )

    async def get_draft(self, project_id: str) -> Optional[BlueprintDraft]:
        """
        获取蓝图草稿

        Args:
            project_id: 项目ID

        Returns:
            草稿对象，如果不存在则返回None
        """
        logger.info("获取蓝图草稿", extra={"project_id": project_id})

        # 查询项目
        result = await self.session.execute(
            select(NovelProject).where(NovelProject.id == project_id)
        )
        project = result.scalar_one_or_none()

        if not project or not project.metadata:
            logger.info("草稿不存在", extra={"project_id": project_id})
            return None

        draft_data = project.metadata.get("blueprint_draft")
        if not draft_data:
            return None

        # 构建 BlueprintDraft 对象
        from ...schemas.blueprint_stage import Stage1Data, Stage2Data, Stage3Data, Stage4Data

        try:
            draft = BlueprintDraft(
                project_id=project_id,
                current_stage=draft_data.get("current_stage", 1),
                stage1=Stage1Data(**draft_data["stage1"]) if draft_data.get("stage1") else None,
                stage2=Stage2Data(**draft_data["stage2"]) if draft_data.get("stage2") else None,
                stage3=Stage3Data(**draft_data["stage3"]) if draft_data.get("stage3") else None,
                stage4=Stage4Data(**draft_data["stage4"]) if draft_data.get("stage4") else None,
                updated_at=draft_data.get("updated_at")
            )
            logger.info(f"草稿获取成功 - project_id={project_id}, current_stage={draft.current_stage}")
            return draft
        except Exception as e:
            logger.error(f"构建草稿对象失败 - project_id={project_id}, error={str(e)}")
            raise

    async def delete_draft(self, project_id: str) -> bool:
        """
        删除蓝图草稿

        Args:
            project_id: 项目ID

        Returns:
            是否删除成功
        """
        logger.info("删除蓝图草稿", extra={"project_id": project_id})

        # 查询项目
        result = await self.session.execute(
            select(NovelProject).where(NovelProject.id == project_id)
        )
        project = result.scalar_one_or_none()

        if not project or not project.metadata:
            logger.info("草稿不存在，无需删除", extra={"project_id": project_id})
            return False

        # 删除草稿数据
        if "blueprint_draft" in project.metadata:
            del project.metadata["blueprint_draft"]
            # 显式标记 metadata_ 字段已修改
            attributes.flag_modified(project, "metadata_")
            await self.session.commit()
            logger.info("草稿删除成功", extra={"project_id": project_id})
            return True

        logger.info("草稿不存在，无需删除", extra={"project_id": project_id})
        return False

    async def has_draft(self, project_id: str) -> bool:
        """
        检查是否存在草稿

        Args:
            project_id: 项目ID

        Returns:
            是否存在草稿
        """
        result = await self.session.execute(
            select(NovelProject).where(NovelProject.id == project_id)
        )
        project = result.scalar_one_or_none()

        if not project or not project.metadata:
            return False

        return "blueprint_draft" in project.metadata

