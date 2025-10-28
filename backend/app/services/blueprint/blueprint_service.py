"""
蓝图生成服务
7步分步生成流程（借鉴LangGraph设计思想）
"""

import asyncio
import json
import re
import logging
from typing import Dict, Any, List, Optional, Callable, Awaitable
from sqlalchemy.ext.asyncio import AsyncSession

from ..llm_service import LLMService
from ...repositories.novel_repository import NovelRepository

logger = logging.getLogger(__name__)


class BlueprintService:
    """
    蓝图生成服务
    7步分步生成蓝图
    """

    def __init__(
        self,
        session: AsyncSession,
    ):
        self.session = session
        self.llm_service = LLMService(session)
        self.novel_repo = NovelRepository(session)

    async def _execute_with_retry(
        self,
        step_func: Callable,
        step_name: str,
        *args,
        max_retries: int = 3,
        **kwargs
    ) -> Any:
        """
        执行步骤，失败时自动重试

        Args:
            step_func: 要执行的步骤函数
            step_name: 步骤名称，用于日志
            *args: 传递给step_func的位置参数
            max_retries: 最大重试次数（关键字参数）
            **kwargs: 传递给step_func的关键字参数

        Returns:
            步骤执行结果

        Raises:
            最后一次失败的异常
        """
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"{step_name}: 开始执行 (尝试 {attempt}/{max_retries})")
                result = await step_func(*args, **kwargs)

                if attempt > 1:
                    logger.info(f"{step_name}: 重试成功 (尝试 {attempt}/{max_retries})")

                return result

            except Exception as e:
                last_error = e
                logger.warning(
                    f"{step_name}: 执行失败 (尝试 {attempt}/{max_retries})",
                    extra={
                        "error": str(e),
                        "attempt": attempt,
                        "max_retries": max_retries
                    }
                )

                # 如果还有重试机会，等待后重试（指数退避）
                if attempt < max_retries:
                    wait_time = 2 ** (attempt - 1)  # 1s, 2s, 4s...
                    logger.info(f"{step_name}: {wait_time}秒后重试...")
                    await asyncio.sleep(wait_time)
                else:
                    # 最后一次尝试失败，记录错误并抛出
                    logger.error(
                        f"{step_name}: 重试{max_retries}次后仍然失败",
                        extra={"error": str(e)}
                    )

        # 抛出最后一次的异常
        raise last_error

    def _extract_json_from_response(self, response: str) -> Dict[str, Any]:
        """
        从LLM响应中提取JSON内容
        支持处理DeepSeek-R1等模型返回的包含思考过程的响应
        """
        from ...utils.json_utils import remove_think_tags

        # 先移除 <think> 标签
        response = remove_think_tags(response)

        normalized_response = response.replace('"', '"').replace('"', '"').replace(''', "'").replace(''', "'")

        try:
            return json.loads(normalized_response)
        except json.JSONDecodeError:
            pass

        json_patterns = [
            r'```json\s*(\{.*\})\s*```',  # 贪婪匹配，捕获完整的嵌套JSON
            r'```\s*(\{.*\})\s*```',       # 贪婪匹配，无json标记
            r'(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})',  # 递归匹配嵌套括号
        ]

        for pattern in json_patterns:
            matches = re.findall(pattern, normalized_response, re.DOTALL)
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue

        logger.error("无法从响应中提取有效JSON", extra={"full_response": response})
        raise ValueError(f"无法解析LLM响应为JSON，完整响应:\n{response}")

    async def generate_blueprint(
        self,
        conversation_history: List[Dict[str, str]],
        project_id: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        生成完整蓝图

        Args:
            conversation_history: 对话历史
            project_id: 项目ID（可选）
            progress_callback: 进度回调函数，接收(step, total, message)

        Returns:
            生成的蓝图数据
        """
        logger.info("开始生成蓝图", extra={
            "project_id": project_id,
            "conversation_count": len(conversation_history)
        })

        state = {}
        errors = []
        total_steps = 7

        try:
            if progress_callback:
                await progress_callback(1, total_steps, "生成基础信息")
            state = await self._execute_with_retry(
                self._step1_generate_basic_info,
                "步骤1: 生成基础信息",
                state, conversation_history
            )

            if progress_callback:
                await progress_callback(2, total_steps, "构建故事梗概")
            state = await self._execute_with_retry(
                self._step2_generate_synopsis,
                "步骤2: 构建故事梗概",
                state, conversation_history
            )

            if progress_callback:
                await progress_callback(3, total_steps, "设计世界观设定")
            state = await self._execute_with_retry(
                self._step3_generate_world_setting,
                "步骤3: 设计世界观设定",
                state
            )

            if progress_callback:
                await progress_callback(4, total_steps, "创建角色列表")
            state = await self._execute_with_retry(
                self._step4_generate_characters,
                "步骤4: 创建角色列表",
                state
            )

            if progress_callback:
                await progress_callback(5, total_steps, "建立角色关系")
            state = await self._execute_with_retry(
                self._step5_generate_relationships,
                "步骤5: 建立角色关系",
                state
            )

            if progress_callback:
                await progress_callback(6, total_steps, "规划章节大纲")
            state = await self._execute_with_retry(
                self._step6_generate_chapter_outline,
                "步骤6: 规划章节大纲",
                state
            )

            if progress_callback:
                await progress_callback(7, total_steps, "组装最终蓝图")
            final_blueprint = await self._execute_with_retry(
                self._step7_assemble_and_validate,
                "步骤7: 组装最终蓝图",
                state
            )

            if project_id:
                await self._save_blueprint_to_db(project_id, final_blueprint)

            logger.info("蓝图生成完成", extra={
                "project_id": project_id,
                "characters_count": len(final_blueprint.get("characters", [])),
                "chapters_count": len(final_blueprint.get("chapter_outline", []))
            })

            return final_blueprint

        except Exception as e:
            logger.error("蓝图生成失败", extra={
                "error": str(e),
                "project_id": project_id,
                "errors": errors
            })
            raise

    async def _step1_generate_basic_info(
        self,
        state: Dict,
        conversation_history: List[Dict[str, str]]
    ) -> Dict:
        """生成基础信息"""
        logger.info("执行步骤1: 生成基础信息")

        from ...prompts.blueprint import step1_basic_info

        system_prompt, user_prompt = step1_basic_info.build_prompt(
            conversation_history
        )

        response = await self.llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=[{"role": "user", "content": user_prompt}]
        )

        try:
            data = self._extract_json_from_response(response)
            if not all(k in data for k in ["title", "genre", "tone"]):
                raise ValueError("缺少必需字段")

            state["basic_info"] = data
            logger.info("基础信息生成成功", extra={"title": data.get("title")})
            return state
        except Exception as e:
            logger.error("基础信息解析失败", extra={"error": str(e), "full_response": response})
            raise

    async def _step2_generate_synopsis(
        self,
        state: Dict,
        conversation_history: List[Dict[str, str]]
    ) -> Dict:
        """生成故事梗概"""
        logger.info("执行步骤2: 生成故事梗概")

        from ...prompts.blueprint import step2_synopsis

        system_prompt, user_prompt = step2_synopsis.build_prompt(
            conversation_history=conversation_history,
            basic_info=state["basic_info"]
        )

        response = await self.llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=[{"role": "user", "content": user_prompt}]
        )

        try:
            data = self._extract_json_from_response(response)

            # 验证必需字段
            required_fields = [
                "story_background",
                "protagonist_start",
                "core_conflict",
                "development_expectation",
                "structure_plan"
            ]
            missing = [f for f in required_fields if f not in data]
            if missing:
                raise ValueError(f"缺少必需字段: {missing}")

            # 组装 full_synopsis
            full_synopsis = (
                f"【故事背景】\n{data['story_background']}\n\n"
                f"【主角起点】\n{data['protagonist_start']}\n\n"
                f"【核心冲突】\n{data['core_conflict']}\n\n"
                f"【发展预期】\n{data['development_expectation']}\n\n"
                f"【结构规划】\n{data['structure_plan']}"
            )

            state["full_synopsis"] = full_synopsis
            logger.info("故事梗概生成成功")
            return state
        except Exception as e:
            logger.error("故事梗概解析失败", extra={"error": str(e)})
            raise

    async def _step3_generate_world_setting(self, state: Dict) -> Dict:
        """生成世界观设定"""
        logger.info("执行步骤3: 生成世界观设定")

        from ...prompts.blueprint import step3_world_setting

        system_prompt, user_prompt = step3_world_setting.build_prompt(
            basic_info=state["basic_info"],
            synopsis=state["full_synopsis"]
        )

        response = await self.llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=[{"role": "user", "content": user_prompt}]
        )

        try:
            data = self._extract_json_from_response(response)

            # 验证world_setting字段
            if "world_setting" not in data:
                raise ValueError("缺少world_setting字段")

            world_setting = data["world_setting"]

            # 验证必需的子字段
            required_fields = ["core_rules", "key_locations", "factions"]
            missing = [f for f in required_fields if f not in world_setting]
            if missing:
                raise ValueError(f"world_setting缺少必需字段: {missing}")

            # 验证数组长度
            if not isinstance(world_setting["core_rules"], list) or len(world_setting["core_rules"]) != 3:
                raise ValueError(f"core_rules应包含3条规则，实际: {len(world_setting.get('core_rules', []))}")

            if not isinstance(world_setting["key_locations"], list) or not (3 <= len(world_setting["key_locations"]) <= 4):
                raise ValueError(f"key_locations应包含3-4个地点，实际: {len(world_setting.get('key_locations', []))}")

            if not isinstance(world_setting["factions"], list) or not (2 <= len(world_setting["factions"]) <= 3):
                raise ValueError(f"factions应包含2-3个势力，实际: {len(world_setting.get('factions', []))}")

            state["world_setting"] = world_setting
            logger.info("世界观设定生成成功", extra={
                "core_rules_count": len(world_setting["core_rules"]),
                "key_locations_count": len(world_setting["key_locations"]),
                "factions_count": len(world_setting["factions"])
            })
            return state
        except Exception as e:
            logger.error("世界观设定解析失败", extra={"error": str(e)})
            raise

    async def _step4_generate_characters(self, state: Dict) -> Dict:
        """生成角色列表"""
        logger.info("执行步骤4: 生成角色列表")

        from ...prompts.blueprint import step4_characters

        system_prompt, user_prompt = step4_characters.build_prompt(
            basic_info=state["basic_info"],
            synopsis=state["full_synopsis"],
            world_setting=state["world_setting"]
        )

        response = await self.llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=[{"role": "user", "content": user_prompt}]
        )

        try:
            data = self._extract_json_from_response(response)
            characters = data.get("characters", [])
            if not isinstance(characters, list) or len(characters) == 0:
                raise ValueError("角色数据无效")

            state["characters"] = characters
            logger.info("角色列表生成成功", extra={"count": len(characters)})
            return state
        except Exception as e:
            logger.error("角色列表解析失败", extra={"error": str(e)})
            raise

    async def _step5_generate_relationships(self, state: Dict) -> Dict:
        """生成角色关系"""
        logger.info("执行步骤5: 生成角色关系")

        from ...prompts.blueprint import step5_relationships

        system_prompt, user_prompt = step5_relationships.build_prompt(
            characters=state["characters"]
        )

        response = await self.llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=[{"role": "user", "content": user_prompt}]
        )

        try:
            data = self._extract_json_from_response(response)
            state["relationships"] = data.get("relationships", [])
            logger.info("角色关系生成成功", extra={"count": len(state["relationships"])})
            return state
        except Exception as e:
            logger.error("角色关系解析失败", extra={"error": str(e)})
            raise

    async def _step6_generate_chapter_outline(self, state: Dict) -> Dict:
        """生成章节大纲"""
        logger.info("执行步骤6: 生成章节大纲")

        from ...prompts.blueprint import step6_chapter_outline

        system_prompt, user_prompt = step6_chapter_outline.build_prompt(
            basic_info=state["basic_info"],
            synopsis=state["full_synopsis"],
            world_setting=state["world_setting"],
            characters=state["characters"],
            relationships=state["relationships"]
        )

        response = await self.llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=[{"role": "user", "content": user_prompt}]
        )

        try:
            data = self._extract_json_from_response(response)
            chapter_outline = data.get("chapter_outline", [])
            if not isinstance(chapter_outline, list) or len(chapter_outline) == 0:
                raise ValueError("章节大纲数据无效")

            state["chapter_outline"] = chapter_outline
            logger.info("章节大纲生成成功", extra={"count": len(chapter_outline)})
            return state
        except Exception as e:
            logger.error("章节大纲解析失败", extra={"error": str(e)})
            raise

    async def _step7_assemble_and_validate(self, state: Dict) -> Dict:
        """组装最终蓝图"""
        logger.info("执行步骤7: 组装最终蓝图")

        # 验证所有字段
        required_fields = [
            "basic_info",
            "full_synopsis",
            "world_setting",
            "characters",
            "relationships",
            "chapter_outline"
        ]

        missing = [f for f in required_fields if f not in state or not state[f]]
        if missing:
            raise ValueError(f"缺少必需数据: {missing}")

        # 组装蓝图
        final_blueprint = {
            **state["basic_info"],
            "full_synopsis": state["full_synopsis"],
            "world_setting": state["world_setting"],
            "characters": state["characters"],
            "relationships": state["relationships"],
            "chapter_outline": state["chapter_outline"],
        }

        logger.info("蓝图组装完成")
        return final_blueprint

    async def _save_blueprint_to_db(
        self,
        project_id: str,
        blueprint: Dict[str, Any]
    ) -> None:
        """保存蓝图到数据库的关联表结构"""
        from ...models.novel import (
            NovelBlueprint, BlueprintCharacter,
            BlueprintRelationship, ChapterOutline
        )

        try:
            project = await self.novel_repo.get_by_id(project_id)
            if not project:
                raise ValueError(f"项目不存在: {project_id}")

            existing_blueprint = project.blueprint
            if existing_blueprint:
                existing_blueprint.title = blueprint.get("title")
                existing_blueprint.target_audience = blueprint.get("target_audience")
                existing_blueprint.genre = blueprint.get("genre")
                existing_blueprint.style = blueprint.get("style")
                existing_blueprint.tone = blueprint.get("tone")
                existing_blueprint.one_sentence_summary = blueprint.get("one_sentence_summary")
                existing_blueprint.full_synopsis = blueprint.get("full_synopsis")
                existing_blueprint.world_setting = blueprint.get("world_setting", {})
            else:
                new_blueprint = NovelBlueprint(
                    project_id=project_id,
                    title=blueprint.get("title"),
                    target_audience=blueprint.get("target_audience"),
                    genre=blueprint.get("genre"),
                    style=blueprint.get("style"),
                    tone=blueprint.get("tone"),
                    one_sentence_summary=blueprint.get("one_sentence_summary"),
                    full_synopsis=blueprint.get("full_synopsis"),
                    world_setting=blueprint.get("world_setting", {})
                )
                self.session.add(new_blueprint)

            for char_data in blueprint.get("characters", []):
                char = BlueprintCharacter(
                    project_id=project_id,
                    name=char_data.get("name"),
                    identity=char_data.get("identity"),
                    personality=char_data.get("personality"),
                    goals=char_data.get("goals"),
                    abilities=char_data.get("abilities"),
                    relationship_to_protagonist=char_data.get("relationship_to_protagonist"),
                    extra=char_data.get("extra"),
                    position=char_data.get("position", 0)
                )
                self.session.add(char)

            for rel_data in blueprint.get("relationships", []):
                # 验证必填字段
                char_from = rel_data.get("character_from") or rel_data.get("from")
                char_to = rel_data.get("character_to") or rel_data.get("to")

                if not char_from or not char_to:
                    logger.warning("跳过无效关系数据", extra={"rel_data": rel_data})
                    continue

                rel = BlueprintRelationship(
                    project_id=project_id,
                    character_from=char_from,
                    character_to=char_to,
                    description=rel_data.get("description"),
                    position=rel_data.get("position", 0)
                )
                self.session.add(rel)

            for idx, chapter_data in enumerate(blueprint.get("chapter_outline", [])):
                outline = ChapterOutline(
                    project_id=project_id,
                    chapter_number=idx + 1,
                    title=chapter_data.get("title"),
                    summary=chapter_data.get("summary")
                )
                self.session.add(outline)

            await self.session.commit()
            logger.info("蓝图已保存到数据库", extra={"project_id": project_id})

        except Exception as e:
            await self.session.rollback()
            logger.error("保存蓝图失败", extra={
                "project_id": project_id,
                "error": str(e)
            })
            raise
            # 不抛出异常，因为蓝图已生成成功
