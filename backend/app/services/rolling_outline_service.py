"""分卷管理服务.

提供两个核心功能：
1. 检查分卷完成度（判断分卷是否已经完成）
2. 生成下一卷大纲（当前分卷完成后生成下一卷）
"""

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.novel import StoryFramework, VolumeOutline
from ..prompts.blueprint import generate_next_volume, volume_completion_check
from ..services.llm_service import LLMService
from ..utils.json_utils import remove_think_tags, unwrap_markdown_json

logger = logging.getLogger(__name__)


class RollingOutlineService:
    """分卷管理服务."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm_service = LLMService(session)

    async def check_volume_completion(
        self,
        project_id: str,
        volume_id: int,
        written_chapters: list[dict[str, Any]],
        user_id: int,
    ) -> dict[str, Any]:
        """检查分卷完成度.

        Args:
            project_id: 项目 ID
            volume_id: 分卷 ID
            written_chapters: 已写章节列表（包含 chapter_number, title, actual_content）
            user_id: 用户 ID

        Returns:
            包含 is_completed, completion_percentage, criteria_status 等的字典

        """
        logger.info(f"检查分卷完成度：项目 {project_id}，分卷 {volume_id}")

        # 1. 获取分卷大纲
        volume_outline = await self._get_volume_outline_by_id(volume_id)
        if not volume_outline:
            raise ValueError(f"未找到分卷 {volume_id}")

        # 2. 构建提示词
        system_prompt, user_prompt = volume_completion_check.build_prompt(
            volume_outline=self._volume_to_dict(volume_outline),
            written_chapters=written_chapters,
        )

        # 3. 调用 LLM
        logger.info("调用 LLM 检查分卷完成度")
        response = await self.llm_service.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.3,  # 较低温度，更客观的分析
            user_id=user_id,
            timeout=300.0,
        )

        # 4. 解析响应
        cleaned = remove_think_tags(response)
        unwrapped = unwrap_markdown_json(cleaned)
        result = json.loads(unwrapped)

        logger.info(
            f"分卷完成度检查结果：{'已完成' if result.get('is_completed') else '未完成'}"
        )

        return result

    async def generate_next_volume_outline(
        self,
        project_id: str,
        previous_volume_id: int,
        story_context: dict[str, Any],
        user_id: int,
    ) -> dict[str, Any]:
        """生成下一卷大纲.

        Args:
            project_id: 项目 ID
            previous_volume_id: 上一卷的 ID
            story_context: 故事上下文（包含 title, genre, world_setting, characters 等）
            user_id: 用户 ID

        Returns:
            下一卷大纲的字典

        """
        logger.info(f"生成下一卷大纲：项目 {project_id}，上一卷 {previous_volume_id}")

        # 1. 获取总体框架
        story_framework = await self._get_story_framework(project_id)
        if not story_framework:
            raise ValueError(f"未找到项目 {project_id} 的总体框架")

        # 2. 获取已完成分卷列表
        completed_volumes = await self._get_completed_volumes(project_id)

        # 3. 确定下一卷的卷号
        next_volume_number = len(completed_volumes) + 1

        # 4. 构建提示词
        system_prompt, user_prompt = generate_next_volume.build_prompt(
            overall_arc=story_framework.overall_arc,
            completed_volumes=[self._volume_to_dict(v) for v in completed_volumes],
            next_volume_number=next_volume_number,
            story_context=story_context,
        )

        # 5. 调用 LLM
        logger.info(f"调用 LLM 生成第 {next_volume_number} 卷大纲")
        response = await self.llm_service.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,
            user_id=user_id,
            timeout=300.0,
        )

        # 6. 解析响应
        cleaned = remove_think_tags(response)
        unwrapped = unwrap_markdown_json(cleaned)
        result = json.loads(unwrapped)

        logger.info(
            f"成功生成第 {next_volume_number} 卷大纲：{result.get('volume_title')}"
        )

        return result

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    async def _get_current_volume_outline(
        self, project_id: str, chapter_number: int
    ) -> VolumeOutline | None:
        """获取包含指定章节的分卷大纲."""
        stmt = (
            select(VolumeOutline)
            .where(
                VolumeOutline.project_id == project_id,
                VolumeOutline.actual_start_chapter <= chapter_number,
                (VolumeOutline.actual_end_chapter >= chapter_number)
                | (VolumeOutline.actual_end_chapter.is_(None)),
            )
            .order_by(VolumeOutline.volume_number)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def _get_volume_outline_by_id(self, volume_id: int) -> VolumeOutline | None:
        """根据 ID 获取分卷大纲."""
        return await self.session.get(VolumeOutline, volume_id)

    async def _get_story_framework(self, project_id: str) -> StoryFramework | None:
        """获取总体框架."""
        stmt = select(StoryFramework).where(StoryFramework.project_id == project_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def _get_completed_volumes(self, project_id: str) -> list[VolumeOutline]:
        """获取已完成的分卷列表."""
        stmt = (
            select(VolumeOutline)
            .where(
                VolumeOutline.project_id == project_id,
                VolumeOutline.status == "completed",
            )
            .order_by(VolumeOutline.volume_number)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def _volume_to_dict(self, volume: VolumeOutline) -> dict[str, Any]:
        """将 VolumeOutline 模型转换为字典."""
        return {
            "volume_number": volume.volume_number,
            "volume_title": volume.volume_title,
            "volume_goal": volume.volume_goal,
            "estimated_chapters": volume.estimated_chapters,
            "actual_start_chapter": volume.actual_start_chapter,
            "actual_end_chapter": volume.actual_end_chapter,
            "completion_criteria": volume.completion_criteria or [],
            "major_arcs": volume.major_arcs or [],
            "new_characters": volume.new_characters or [],
            "foreshadowing": volume.foreshadowing or [],
            "status": volume.status,
        }
