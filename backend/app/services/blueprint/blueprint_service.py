"""蓝图生成服务.

7步分步生成流程（借鉴LangGraph设计思想）。
"""


import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ...repositories.novel_repository import NovelRepository
from ..llm_service import LLMService

logger = logging.getLogger(__name__)


class BlueprintService:
    """蓝图生成服务.

    7步分步生成蓝图。
    """

    def __init__(
        self,
        session: AsyncSession,
    ):
        self.session = session
        self.llm_service = LLMService(session)
        self.novel_repo = NovelRepository(session)

    async def _execute_with_retry(
        self, step_func: Callable, step_name: str, *args, max_retries: int = 3, **kwargs
    ) -> Any:
        """执行步骤，失败时自动重试.

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
                        "max_retries": max_retries,
                    },
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
                        extra={"error": str(e)},
                    )

        # 抛出最后一次的异常
        raise last_error

    def _extract_json_from_response(self, response: str) -> dict[str, Any]:
        """从LLM响应中提取JSON内容.

        支持处理DeepSeek-R1等模型返回的包含思考过程的响应。
        """
        from ...utils.json_utils import remove_think_tags

        # 先移除 <think> 标签
        response = remove_think_tags(response)

        normalized_response = (
            response.replace('"', '"')
            .replace('"', '"')
            .replace(""", "'").replace(""", "'")
        )

        try:
            return json.loads(normalized_response)
        except json.JSONDecodeError:
            pass

        json_patterns = [
            r"```json\s*(\{.*\})\s*```",  # 贪婪匹配，捕获完整的嵌套JSON
            r"```\s*(\{.*\})\s*```",  # 贪婪匹配，无json标记
            r"(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})",  # 递归匹配嵌套括号
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
        conversation_history: list[dict[str, str]],
        project_id: str | None = None,
        progress_callback: Callable[[int, int, str], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """生成完整蓝图（事件驱动模式）.

        Args:
            conversation_history: 对话历史
            project_id: 项目ID（可选）
            progress_callback: 进度回调函数，接收(step, total, message)

        Returns:
            生成的蓝图数据

        """
        logger.info(
            "开始生成蓝图（事件驱动模式）",
            extra={
                "project_id": project_id,
                "conversation_count": len(conversation_history),
            },
        )

        state = {}
        errors = []
        total_steps = 8  # 增加到 8 步（新增 Step 6A）

        try:
            if progress_callback:
                await progress_callback(1, total_steps, "生成基础信息")
            state = await self._execute_with_retry(
                self._step1_generate_basic_info,
                "步骤1: 生成基础信息",
                state,
                conversation_history,
            )

            if progress_callback:
                await progress_callback(2, total_steps, "构建故事梗概")
            state = await self._execute_with_retry(
                self._step2_generate_synopsis,
                "步骤2: 构建故事梗概",
                state,
                conversation_history,
            )

            if progress_callback:
                await progress_callback(3, total_steps, "设计世界观设定")
            state = await self._execute_with_retry(
                self._step3_generate_world_setting, "步骤3: 设计世界观设定", state
            )

            if progress_callback:
                await progress_callback(4, total_steps, "创建角色列表")
            state = await self._execute_with_retry(
                self._step4_generate_characters, "步骤4: 创建角色列表", state
            )

            if progress_callback:
                await progress_callback(5, total_steps, "建立角色关系")
            state = await self._execute_with_retry(
                self._step5_generate_relationships, "步骤5: 建立角色关系", state
            )

            # 新增 Step 6A：生成第一卷大纲
            if progress_callback:
                await progress_callback(6, total_steps, "生成第一卷大纲")
            state = await self._execute_with_retry(
                self._step6a_generate_volume_outline, "步骤6A: 生成第一卷大纲", state
            )

            # Step 6B：生成情节事件
            if progress_callback:
                await progress_callback(7, total_steps, "生成情节事件")
            state = await self._execute_with_retry(
                self._step6b_generate_plot_events, "步骤6B: 生成情节事件", state
            )

            if progress_callback:
                await progress_callback(8, total_steps, "组装最终蓝图")
            final_blueprint = await self._execute_with_retry(
                self._step7_assemble_and_validate, "步骤7: 组装最终蓝图", state
            )

            if project_id:
                await self._save_blueprint_to_db(project_id, final_blueprint)

            logger.info(
                "蓝图生成完成",
                extra={
                    "project_id": project_id,
                    "characters_count": len(final_blueprint.get("characters", [])),
                    "events_count": len(final_blueprint.get("plot_events", [])),
                },
            )

            return final_blueprint

        except Exception as e:
            logger.error(
                "蓝图生成失败",
                extra={"error": str(e), "project_id": project_id, "errors": errors},
            )
            raise

    async def _step1_generate_basic_info(
        self, state: dict, conversation_history: list[dict[str, str]]
    ) -> dict:
        """生成基础信息."""
        logger.info("执行步骤1: 生成基础信息")

        from ...prompts.blueprint import step1_basic_info

        system_prompt, user_prompt = step1_basic_info.build_prompt(conversation_history)

        response = await self.llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=[{"role": "user", "content": user_prompt}],
        )

        try:
            data = self._extract_json_from_response(response)
            if not all(k in data for k in ["title", "genre", "tone"]):
                raise ValueError("缺少必需字段")

            state["basic_info"] = data
            logger.info("基础信息生成成功", extra={"title": data.get("title")})
            return state
        except Exception as e:
            logger.error(
                "基础信息解析失败", extra={"error": str(e), "full_response": response}
            )
            raise

    async def _step2_generate_synopsis(
        self, state: dict, conversation_history: list[dict[str, str]]
    ) -> dict:
        """生成故事梗概."""
        logger.info("执行步骤2: 生成故事梗概")

        from ...prompts.blueprint import step2_synopsis

        system_prompt, user_prompt = step2_synopsis.build_prompt(
            conversation_history=conversation_history, basic_info=state["basic_info"]
        )

        response = await self.llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=[{"role": "user", "content": user_prompt}],
        )

        try:
            data = self._extract_json_from_response(response)

            # 验证必需字段
            required_fields = [
                "story_background",
                "protagonist_start",
                "core_conflict",
                "development_expectation",
                "structure_plan",
                "overall_arc",  # 新增：三幕结构
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

            # 新增：保存三幕结构和预估总章节数
            state["overall_arc"] = data.get("overall_arc", {})
            state["estimated_total_chapters"] = data.get("estimated_total_chapters")

            logger.info(
                "故事梗概生成成功",
                extra={
                    "has_overall_arc": bool(state["overall_arc"]),
                    "estimated_total_chapters": state.get("estimated_total_chapters"),
                },
            )
            return state
        except Exception as e:
            logger.error("故事梗概解析失败", extra={"error": str(e)})
            raise

    async def _step3_generate_world_setting(self, state: dict) -> dict:
        """生成世界观设定."""
        logger.info("执行步骤3: 生成世界观设定")

        from ...prompts.blueprint import step3_world_setting

        system_prompt, user_prompt = step3_world_setting.build_prompt(
            basic_info=state["basic_info"], synopsis=state["full_synopsis"]
        )

        response = await self.llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=[{"role": "user", "content": user_prompt}],
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
            if (
                not isinstance(world_setting["core_rules"], list)
                or len(world_setting["core_rules"]) != 3
            ):
                raise ValueError(
                    f"core_rules应包含3条规则，实际: {len(world_setting.get('core_rules', []))}"
                )

            if not isinstance(world_setting["key_locations"], list) or not (
                3 <= len(world_setting["key_locations"]) <= 4
            ):
                raise ValueError(
                    f"key_locations应包含3-4个地点，实际: {len(world_setting.get('key_locations', []))}"
                )

            if not isinstance(world_setting["factions"], list) or not (
                2 <= len(world_setting["factions"]) <= 3
            ):
                raise ValueError(
                    f"factions应包含2-3个势力，实际: {len(world_setting.get('factions', []))}"
                )

            state["world_setting"] = world_setting
            logger.info(
                "世界观设定生成成功",
                extra={
                    "core_rules_count": len(world_setting["core_rules"]),
                    "key_locations_count": len(world_setting["key_locations"]),
                    "factions_count": len(world_setting["factions"]),
                },
            )
            return state
        except Exception as e:
            logger.error("世界观设定解析失败", extra={"error": str(e)})
            raise

    async def _step4_generate_characters(self, state: dict) -> dict:
        """生成角色列表."""
        logger.info("执行步骤4: 生成角色列表")

        from ...prompts.blueprint import step4_characters

        system_prompt, user_prompt = step4_characters.build_prompt(
            basic_info=state["basic_info"],
            synopsis=state["full_synopsis"],
            world_setting=state["world_setting"],
        )

        response = await self.llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=[{"role": "user", "content": user_prompt}],
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

    async def _step5_generate_relationships(self, state: dict) -> dict:
        """生成角色关系."""
        logger.info("执行步骤5: 生成角色关系")

        from ...prompts.blueprint import step5_relationships

        system_prompt, user_prompt = step5_relationships.build_prompt(
            characters=state["characters"]
        )

        response = await self.llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=[{"role": "user", "content": user_prompt}],
        )

        try:
            data = self._extract_json_from_response(response)
            state["relationships"] = data.get("relationships", [])
            logger.info(
                "角色关系生成成功", extra={"count": len(state["relationships"])}
            )
            return state
        except Exception as e:
            logger.error("角色关系解析失败", extra={"error": str(e)})
            raise

    async def _step6a_generate_volume_outline(self, state: dict) -> dict:
        """生成第一卷大纲（新增）."""
        logger.info("执行步骤6A: 生成第一卷大纲")

        from ...prompts.blueprint import step6a_volume_outline

        # 从 Step 2 的结果中提取 overall_arc 和 estimated_total_chapters
        overall_arc = state.get("overall_arc", {})
        estimated_total_chapters = state.get("estimated_total_chapters")

        system_prompt, user_prompt = step6a_volume_outline.build_prompt(
            title=state["basic_info"].get("title", ""),
            genre=state["basic_info"].get("genre", ""),
            tone=state["basic_info"].get("tone", ""),
            full_synopsis=state["full_synopsis"],
            overall_arc=overall_arc,
            world_setting=state["world_setting"],
            characters=state["characters"],
            estimated_total_chapters=estimated_total_chapters,
        )

        response = await self.llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=[{"role": "user", "content": user_prompt}],
        )

        try:
            data = self._extract_json_from_response(response)

            # 验证必需字段
            required_fields = [
                "volume_number",
                "volume_title",
                "volume_goal",
                "major_arcs",
            ]
            missing = [f for f in required_fields if f not in data]
            if missing:
                raise ValueError(f"分卷大纲缺少必需字段: {missing}")

            state["volume_outline"] = data
            logger.info(
                "第一卷大纲生成成功",
                extra={
                    "volume_title": data.get("volume_title"),
                    "estimated_chapters": data.get("estimated_chapters"),
                    "arcs_count": len(data.get("major_arcs", [])),
                },
            )
            return state
        except Exception as e:
            logger.error("第一卷大纲解析失败", extra={"error": str(e)})
            raise

    async def _step6b_generate_plot_events(self, state: dict) -> dict:
        """生成第一卷的情节事件（事件驱动模式）."""
        logger.info("执行步骤6B: 生成第一卷的情节事件")

        from ...prompts.blueprint import step6b_plot_events

        basic_info = state["basic_info"]
        overall_arc = state.get("overall_arc", {})
        volume_outline = state.get("volume_outline", {})

        system_prompt, user_prompt = step6b_plot_events.build_prompt(
            title=basic_info.get("title", ""),
            genre=basic_info.get("genre", ""),
            tone=basic_info.get("tone", ""),
            overall_arc=overall_arc,
            volume_outline=volume_outline,
            estimated_total_chapters=state.get("estimated_total_chapters"),
        )

        response = await self.llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=[{"role": "user", "content": user_prompt}],
        )

        try:
            data = self._extract_json_from_response(response)
            plot_events = data.get("plot_events", [])
            if not isinstance(plot_events, list) or len(plot_events) == 0:
                raise ValueError("情节事件数据无效")

            # 验证必需字段
            for event in plot_events:
                required_fields = [
                    "event_id",
                    "event_title",
                    "act",
                    "arc_index",
                    "event_type",
                    "description",
                    "key_points",
                    "sequence",
                ]
                missing = [f for f in required_fields if f not in event]
                if missing:
                    raise ValueError(f"事件缺少必需字段: {missing}")

            state["plot_events"] = plot_events
            state["total_events"] = data.get("total_events", len(plot_events))
            state["act_distribution"] = data.get("act_distribution", {})
            logger.info("情节事件生成成功", extra={"count": len(plot_events)})
            return state
        except Exception as e:
            logger.error("情节事件解析失败", extra={"error": str(e)})
            raise

    async def _step7_assemble_and_validate(self, state: dict) -> dict:
        """组装最终蓝图（事件驱动模式）."""
        logger.info("执行步骤7: 组装最终蓝图")

        # 验证所有必需字段
        required_fields = [
            "basic_info",
            "full_synopsis",
            "world_setting",
            "characters",
            "relationships",
            "overall_arc",
            "volume_outline",
            "plot_events",
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
            "overall_arc": state["overall_arc"],
            "estimated_total_chapters": state.get("estimated_total_chapters"),
            "volume_outline": state["volume_outline"],
            "plot_events": state["plot_events"],
            "total_events": state.get("total_events"),
            "act_distribution": state.get("act_distribution"),
        }

        logger.info(
            "蓝图组装完成",
            extra={
                "has_overall_arc": bool(final_blueprint.get("overall_arc")),
                "has_volume_outline": bool(final_blueprint.get("volume_outline")),
                "estimated_total_chapters": final_blueprint.get(
                    "estimated_total_chapters"
                ),
                "events_count": len(final_blueprint.get("plot_events", [])),
            },
        )
        return final_blueprint

    async def _save_blueprint_to_db(
        self, project_id: str, blueprint: dict[str, Any]
    ) -> None:
        """保存蓝图到数据库的关联表结构（事件驱动模式）."""
        from ...models.novel import (
            BlueprintCharacter,
            BlueprintRelationship,
            NovelBlueprint,
            PlotEvent,
            StoryFramework,
            VolumeOutline,
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
                existing_blueprint.one_sentence_summary = blueprint.get(
                    "one_sentence_summary"
                )
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
                    world_setting=blueprint.get("world_setting", {}),
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
                    relationship_to_protagonist=char_data.get(
                        "relationship_to_protagonist"
                    ),
                    extra=char_data.get("extra"),
                    position=char_data.get("position", 0),
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
                    position=rel_data.get("position", 0),
                )
                self.session.add(rel)

            # 新增：保存总体框架（StoryFramework）
            overall_arc = blueprint.get("overall_arc")
            if overall_arc:
                existing_framework = await self.session.get(StoryFramework, project_id)
                if existing_framework:
                    existing_framework.overall_arc = overall_arc
                    existing_framework.estimated_total_chapters = blueprint.get(
                        "estimated_total_chapters"
                    )
                else:
                    framework = StoryFramework(
                        project_id=project_id,
                        overall_arc=overall_arc,
                        estimated_total_chapters=blueprint.get(
                            "estimated_total_chapters"
                        ),
                    )
                    self.session.add(framework)

            # 新增：保存分卷大纲（VolumeOutline）
            volume_outline_data = blueprint.get("volume_outline")
            if volume_outline_data:
                volume = VolumeOutline(
                    project_id=project_id,
                    volume_number=volume_outline_data.get("volume_number", 1),
                    volume_title=volume_outline_data.get("volume_title", ""),
                    arc_phase=volume_outline_data.get(
                        "arc_phase", "opening"
                    ),  # 新增：保存 arc_phase
                    volume_goal=volume_outline_data.get("volume_goal", ""),
                    estimated_chapters=volume_outline_data.get("estimated_chapters"),
                    completion_criteria=volume_outline_data.get("completion_criteria"),
                    major_arcs=volume_outline_data.get("major_arcs"),
                    new_characters=volume_outline_data.get("new_characters"),
                    foreshadowing=volume_outline_data.get("foreshadowing"),
                    status="draft",
                )
                self.session.add(volume)
                await self.session.flush()  # 获取 volume.id
                volume_id = volume.id
            else:
                volume_id = None

            # 保存情节事件
            for event_data in blueprint.get("plot_events", []):
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
                    key_points=event_data.get("key_points"),
                    completed_key_points=event_data.get("completed_key_points", []),
                    pacing=event_data.get("pacing", "medium"),
                    tension_level=event_data.get("tension_level", "medium"),
                    sequence=event_data.get("sequence"),
                    progress=0,
                    status="pending",
                )
                self.session.add(event)

            await self.session.commit()
            logger.info(
                "蓝图已保存到数据库",
                extra={
                    "project_id": project_id,
                    "has_framework": bool(overall_arc),
                    "has_volume": bool(volume_outline_data),
                },
            )

        except Exception as e:
            await self.session.rollback()
            logger.error(
                "保存蓝图失败", extra={"project_id": project_id, "error": str(e)}
            )
            raise
            # 不抛出异常，因为蓝图已生成成功

    # ==================== 分阶段生成方法 ====================

    async def generate_stage1_concept(
        self,
        conversation_history: list[dict[str, str]],
    ) -> dict[str, Any]:
        """阶段1：生成核心概念.

        对应原 Step 1.

        Returns:
            {
                "title": str,
                "genre": str,
                "tone": str,
                "target_audience": str,
                "style": str,
                "one_sentence_summary": str
            }

        """
        logger.info("开始生成阶段1：核心概念")

        state = {}
        state = await self._execute_with_retry(
            self._step1_generate_basic_info,
            "阶段1: 生成核心概念",
            state,
            conversation_history,
        )

        # 从 state["basic_info"] 中提取阶段1需要的字段
        basic_info = state.get("basic_info", {})
        result = {
            "title": basic_info.get("title", ""),
            "genre": basic_info.get("genre", ""),
            "tone": basic_info.get("tone", ""),
            "target_audience": basic_info.get("target_audience", ""),
            "style": basic_info.get("style", ""),
            "one_sentence_summary": basic_info.get("one_sentence_summary", ""),
        }

        logger.info("阶段1生成完成", extra={"title": result["title"]})
        return result

    async def generate_stage2_framework(
        self,
        conversation_history: list[dict[str, str]],
        stage1_data: dict[str, Any],
    ) -> dict[str, Any]:
        """阶段2：生成故事框架.

        对应原 Step 2 + Step 3.

        Args:
            conversation_history: 对话历史
            stage1_data: 阶段1的数据

        Returns:
            {
                "full_synopsis": str,
                "world_setting": dict,
                "overall_arc": dict,  # 新增：三幕结构
                "estimated_total_chapters": int  # 新增：预估总章节数
            }

        """
        logger.info("开始生成阶段2：故事框架")

        # 将阶段1数据放入state，需要包装成 basic_info 格式
        state = {"basic_info": stage1_data.copy()}

        # 执行 Step 2: 生成故事梗概
        state = await self._execute_with_retry(
            self._step2_generate_synopsis,
            "阶段2-步骤1: 构建故事梗概",
            state,
            conversation_history,
        )

        # 执行 Step 3: 生成世界观设定
        state = await self._execute_with_retry(
            self._step3_generate_world_setting, "阶段2-步骤2: 设计世界观设定", state
        )

        result = {
            "full_synopsis": state.get("full_synopsis", ""),
            "world_setting": state.get("world_setting", {}),
            # 新增：返回三层蓝图架构的第 1 层数据
            "overall_arc": state.get("overall_arc", {}),
            "estimated_total_chapters": state.get("estimated_total_chapters"),
        }

        logger.info(
            "阶段2生成完成",
            extra={
                "has_overall_arc": bool(state.get("overall_arc")),
                "estimated_total_chapters": state.get("estimated_total_chapters"),
            },
        )
        return result

    async def generate_stage3_characters(
        self,
        stage1_data: dict[str, Any],
        stage2_data: dict[str, Any],
    ) -> dict[str, Any]:
        """阶段3：生成角色设定.

        对应原 Step 4 + Step 5.

        Args:
            stage1_data: 阶段1的数据
            stage2_data: 阶段2的数据

        Returns:
            {
                "characters": list,
                "relationships": list
            }

        """
        logger.info("开始生成阶段3：角色设定")

        # 合并前面阶段的数据，需要包装 stage1_data 为 basic_info
        state = {"basic_info": stage1_data.copy(), **stage2_data}

        # 执行 Step 4: 生成角色列表
        state = await self._execute_with_retry(
            self._step4_generate_characters, "阶段3-步骤1: 创建角色列表", state
        )

        # 执行 Step 5: 生成角色关系
        state = await self._execute_with_retry(
            self._step5_generate_relationships, "阶段3-步骤2: 建立角色关系", state
        )

        result = {
            "characters": state.get("characters", []),
            "relationships": state.get("relationships", []),
        }

        logger.info(
            "阶段3生成完成",
            extra={
                "characters_count": len(result["characters"]),
                "relationships_count": len(result["relationships"]),
            },
        )
        return result

    async def generate_stage4_events(
        self,
        stage1_data: dict[str, Any],
        stage2_data: dict[str, Any],
        stage3_data: dict[str, Any],
        progress_callback: Callable[[int, int, dict], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """阶段4：生成情节事件（事件驱动模式）.

        对应原 Step 6A + Step 6B（事件版本）.

        Args:
            stage1_data: 阶段1的数据
            stage2_data: 阶段2的数据（包含 overall_arc 和 estimated_total_chapters）
            stage3_data: 阶段3的数据
            progress_callback: 进度回调，接收(event_number, total_events, event_data)

        Returns:
            {
                "overall_arc": dict,  # 三幕结构（来自 stage2）
                "estimated_total_chapters": int,  # 预估总章节数（来自 stage2）
                "volume_outline": dict,  # 第一卷大纲
                "plot_events": list,  # 情节事件列表
                "total_events": int,  # 事件总数
                "act_distribution": dict  # 幕分布
            }

        """
        logger.info("开始生成阶段4：情节事件（事件驱动模式）")

        # 合并所有前面阶段的数据，需要包装 stage1_data 为 basic_info
        state = {"basic_info": stage1_data.copy(), **stage2_data, **stage3_data}

        # 执行 Step 6A: 生成第一卷大纲
        state = await self._execute_with_retry(
            self._step6a_generate_volume_outline, "阶段4-步骤1: 生成第一卷大纲", state
        )

        # 执行 Step 6B: 基于分卷大纲生成情节事件
        state = await self._execute_with_retry(
            self._step6b_generate_plot_events, "阶段4-步骤2: 生成情节事件", state
        )

        plot_events = state.get("plot_events", [])
        volume_outline = state.get("volume_outline", {})
        overall_arc = state.get("overall_arc", {})
        estimated_total_chapters = state.get("estimated_total_chapters")
        total_events = state.get("total_events", len(plot_events))
        act_distribution = state.get("act_distribution", {})

        # 如果提供了进度回调，逐事件推送
        if progress_callback and plot_events:
            total = len(plot_events)
            for idx, event in enumerate(plot_events, 1):
                await progress_callback(idx, total, event)

        result = {
            "overall_arc": overall_arc,
            "estimated_total_chapters": estimated_total_chapters,
            "volume_outline": volume_outline,
            "plot_events": plot_events,
            "total_events": total_events,
            "act_distribution": act_distribution,
        }

        logger.info(
            "阶段4生成完成（事件驱动模式）",
            extra={
                "has_overall_arc": bool(overall_arc),
                "estimated_total_chapters": estimated_total_chapters,
                "has_volume_outline": bool(volume_outline),
                "events_count": len(plot_events),
                "total_events": total_events,
            },
        )
        return result
