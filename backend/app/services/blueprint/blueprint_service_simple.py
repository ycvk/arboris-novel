"""简化的蓝图生成服务.

移植版本.
"""

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...repositories.novel_repository import NovelRepository
from ..llm_service import LLMService

logger = logging.getLogger(__name__)


class SimpleBlueprintService:
    """简化的蓝图生成服务."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm_service = LLMService(session)
        self.novel_repo = NovelRepository(session)

    async def generate_blueprint(
        self,
        conversation_history: list[dict[str, str]],
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """生成完整蓝图."""
        logger.info(
            "开始生成简化蓝图",
            extra={
                "project_id": project_id,
                "conversation_count": len(conversation_history),
            },
        )

        try:
            # 简化的实现：一次性生成所有数据
            system_prompt = (
                "你是一个网络小说创作助手。请基于对话历史生成一个简单的小说蓝图。"
            )
            (
                f"对话历史：{json.dumps(conversation_history, ensure_ascii=False)}"
            )

            response = await self.llm_service.get_llm_response(
                system_prompt=system_prompt,
                conversation_history=conversation_history,
                user_prompt="生成一个简单的小说蓝图，包含标题、类型、角色和章节大纲",
            )

            # 尝试解析JSON响应
            try:
                blueprint = json.loads(response)
            except json.JSONDecodeError:
                # 如果不是JSON，创建基本结构
                blueprint = {
                    "title": "生成的蓝图",
                    "genre": "玄幻",
                    "characters": [{"name": "主角", "role": "主角"}],
                    "chapter_outline": [{"chapter": 1, "title": "第1章"}],
                    "raw_response": response,
                }

            # 保存到数据库（如果提供了project_id）
            if project_id:
                await self._save_to_db(project_id, blueprint)

            logger.info(
                "简化蓝图生成完成",
                extra={"project_id": project_id, "has_blueprint": bool(blueprint)},
            )

            return blueprint

        except Exception as e:
            logger.error(
                "蓝图生成失败", extra={"error": str(e), "project_id": project_id}
            )
            # 返回默认蓝图
            return {"title": "默认蓝图", "genre": "默认类型", "error": str(e)}

    async def _save_to_db(self, project_id: str, blueprint: dict[str, Any]):
        """保存到数据库."""
        try:
            project = await self.novel_repo.get_by_id(project_id)
            if project:
                # 使用metadata字段存储
                if not hasattr(project, "metadata"):
                    project.metadata = {}
                project.metadata["blueprint_data"] = json.dumps(
                    blueprint, ensure_ascii=False
                )
                self.session.add(project)
                await self.session.commit()
                logger.info("蓝图已保存", extra={"project_id": project_id})
        except Exception as e:
            logger.error("保存失败", extra={"error": str(e), "project_id": project_id})
