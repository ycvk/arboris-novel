import asyncio
import json
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from ...core.config import settings
from ...core.dependencies import get_current_user
from ...db.session import AsyncSessionLocal, get_session
from ...models.novel import Chapter
from ...repositories.system_config_repository import SystemConfigRepository
from ...schemas.novel import (
    DeleteChapterRequest,
    EditChapterRequest,
    EvaluateChapterRequest,
    GenerateChapterRequest,
    GenerateNextVolumeRequest,
    SelectVersionRequest,
    VolumeCompletionCheckRequest,
    VolumeCompletionCheckResponse,
)
from ...schemas.novel import (
    NovelProject as NovelProjectSchema,
)
from ...schemas.user import UserInDB
from ...services.chapter_context_service import ChapterContextService
from ...services.chapter_ingest_service import ChapterIngestionService
from ...services.llm_service import LLMService
from ...services.novel_service import NovelService
from ...services.plot_event_service import PlotEventService
from ...services.prompt_service import PromptService
from ...services.rolling_outline_service import RollingOutlineService
from ...services.vector_store_service import VectorStoreService
from ...utils.json_utils import remove_think_tags, unwrap_markdown_json

router = APIRouter(prefix="/api/writer", tags=["Writer"])
logger = logging.getLogger(__name__)


async def _load_project_schema(
    service: NovelService, project_id: str, user_id: int
) -> NovelProjectSchema:
    return await service.get_project_schema(project_id, user_id)


def _extract_tail_excerpt(text: str | None, limit: int = 500) -> str:
    """截取章节结尾文本，默认保留 500 字。."""
    if not text:
        return ""
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[-limit:]


@router.post(
    "/novels/{project_id}/chapters/generate", response_model=NovelProjectSchema
)
async def generate_chapter(
    project_id: str,
    request: GenerateChapterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """生成章节（事件驱动模式）.

    逻辑：
    1. 获取当前正在进行的事件
    2. 根据事件的进度和关键点生成章节
    3. 更新事件进度
    4. 如果事件完成，自动切换到下一个事件
    """
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    logger.info(
        "用户 %s 开始为项目 %s 生成第 %s 章（事件驱动模式）",
        current_user.id,
        project_id,
        request.chapter_number,
    )

    # 获取当前事件
    current_event = await novel_service.get_current_event_for_chapter(
        project_id, request.chapter_number
    )
    if not current_event:
        logger.warning("项目 %s 未找到当前事件，生成流程终止", project_id)
        raise HTTPException(status_code=404, detail="未找到当前事件，请先生成情节事件")

    chapter = await novel_service.get_or_create_chapter(
        project_id, request.chapter_number
    )
    chapter.real_summary = None
    chapter.selected_version_id = None
    chapter.status = "generating"
    chapter.event_id = current_event.id  # 关联事件
    chapter.event_progress = current_event.progress  # 记录当前事件进度
    chapter.act = current_event.act  # 记录所属的幕
    await session.commit()

    # 构建已完成章节的摘要（事件驱动模式）
    chapters_needing_summary = []
    completed_chapters = []
    latest_prev_number = -1
    for existing in project.chapters:
        if existing.chapter_number >= request.chapter_number:
            continue
        if existing.selected_version is None or not existing.selected_version.content:
            continue
        if not existing.real_summary:
            chapters_needing_summary.append(existing)
        else:
            # 事件驱动模式：从关联的事件获取标题
            chapter_title = f"第{existing.chapter_number}章"
            if existing.event:
                chapter_title = existing.event.event_title or chapter_title

            completed_chapters.append(
                {
                    "chapter_number": existing.chapter_number,
                    "title": chapter_title,
                    "summary": existing.real_summary,
                }
            )
            if existing.chapter_number > latest_prev_number:
                latest_prev_number = existing.chapter_number
                _extract_tail_excerpt(
                    existing.selected_version.content
                )

    if chapters_needing_summary:
        # 为避免复用请求级会话/服务，后台任务内部新建会话与服务并按ID重取数据
        chapter_ids = [
            ch.id for ch in chapters_needing_summary if getattr(ch, "id", None)
        ]

        async def generate_missing_summaries_task(
            project_id_: str, chapter_ids_: list[int], user_id_: int
        ):
            try:
                async with AsyncSessionLocal() as bg_session:
                    bg_llm_service = LLMService(bg_session)
                    for ch_id in chapter_ids_:
                        stmt = select(Chapter).where(Chapter.id == ch_id)
                        result = await bg_session.execute(stmt)
                        ch = result.scalars().first()
                        if (
                            not ch
                            or not ch.selected_version
                            or not ch.selected_version.content
                        ):
                            continue
                        summary = await bg_llm_service.get_summary(
                            ch.selected_version.content,
                            temperature=0.15,
                            user_id=user_id_,
                            timeout=180.0,
                        )
                        ch.real_summary = remove_think_tags(summary)
                        await bg_session.commit()
                        logger.info(
                            "后台生成项目 %s 第 %s 章摘要完成",
                            project_id_,
                            ch.chapter_number,
                        )
            except Exception as exc:
                logger.exception("后台生成摘要失败: %s", exc)

        background_tasks.add_task(
            generate_missing_summaries_task, project_id, chapter_ids, current_user.id
        )

    project_schema = await novel_service._serialize_project(project)
    blueprint_dict = project_schema.blueprint.model_dump()

    if "relationships" in blueprint_dict and blueprint_dict["relationships"]:
        for relation in blueprint_dict["relationships"]:
            if "character_from" in relation:
                relation["from"] = relation.pop("character_from")
            if "character_to" in relation:
                relation["to"] = relation.pop("character_to")

    # 蓝图中禁止携带章节级别的细节信息，避免重复传输大段场景或对话内容
    banned_blueprint_keys = {
        "chapter_summaries",
        "chapter_details",
        "chapter_dialogues",
        "chapter_events",
        "conversation_history",
        "character_timelines",
    }
    for key in banned_blueprint_keys:
        if key in blueprint_dict:
            blueprint_dict.pop(key, None)

    writer_prompt = await prompt_service.get_prompt("writing")
    if not writer_prompt:
        logger.error("未配置名为 'writing' 的写作提示词，无法生成章节内容")
        raise HTTPException(
            status_code=500, detail="缺少写作提示词，请联系管理员配置 'writing' 提示词"
        )

    # 初始化向量检索服务，若未配置则自动降级为纯提示词生成
    vector_store: VectorStoreService | None
    if not settings.vector_store_enabled:
        vector_store = None
    else:
        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，RAG 检索被禁用: %s", exc)
            vector_store = None
    context_service = ChapterContextService(
        llm_service=llm_service, vector_store=vector_store
    )

    # 事件驱动模式：使用事件信息构建 RAG 查询
    event_title = current_event.event_title or f"事件{current_event.event_id}"
    event_description = current_event.description or "暂无描述"
    query_parts = [event_title, event_description]
    if request.writing_notes:
        query_parts.append(request.writing_notes)
    rag_query = "\n".join(part for part in query_parts if part)
    rag_context = await context_service.retrieve_for_generation(
        project_id=project_id,
        query_text=rag_query or event_title or event_description or "",
        user_id=current_user.id,
    )
    chunk_count = len(rag_context.chunks) if rag_context and rag_context.chunks else 0
    summary_count = (
        len(rag_context.summaries) if rag_context and rag_context.summaries else 0
    )
    logger.info(
        "项目 %s 第 %s 章检索到 %s 个剧情片段和 %s 条摘要",
        project_id,
        request.chapter_number,
        chunk_count,
        summary_count,
    )
    # 构建事件驱动模式的输入（符合 writing.md 的格式）
    completed_lines = [
        f"- 第{item['chapter_number']}章 - {item['title']}:{item['summary']}"
        for item in completed_chapters
    ]
    completed_section = (
        "\n".join(completed_lines) if completed_lines else "暂无前情摘要"
    )

    # 计算预期的事件进度（简单估算：每章推进 20-30%）
    estimated_progress_after = min(100, current_event.progress + 25)

    # 获取当前卷的 arc_phase（用于节奏控制）
    arc_phase = "opening"  # 默认值
    if current_event.volume:
        arc_phase = current_event.volume.arc_phase

    # 构建事件驱动模式的 JSON 输入
    event_driven_input = {
        "mode": "event",
        "novel_blueprint": blueprint_dict,
        "completed_chapters": completed_section,
        "current_volume": {
            "volume_number": current_event.volume.volume_number
            if current_event.volume
            else 1,
            "volume_title": current_event.volume.volume_title
            if current_event.volume
            else "未知",
            "arc_phase": arc_phase,
        },
        "current_event": {
            "event_id": current_event.event_id,
            "event_title": current_event.event_title,
            "act": current_event.act,
            "arc_phase": arc_phase,  # 新增：从卷继承 arc_phase
            "event_type": current_event.event_type,
            "description": current_event.description,
            "key_points": current_event.key_points or [],
            "completed_key_points": current_event.completed_key_points or [],
            "pacing": current_event.pacing,
            "tension_level": current_event.tension_level,
            "event_progress": current_event.progress,
        },
        "pending": {
            "chapter_number": request.chapter_number,
            "estimated_progress_after": estimated_progress_after,
        },
    }

    # 如果有写作备注，添加到输入中
    if request.writing_notes:
        event_driven_input["writing_notes"] = request.writing_notes

    prompt_input = json.dumps(event_driven_input, ensure_ascii=False, indent=2)
    logger.debug("章节写作提示词（事件驱动模式）：%s\n%s", writer_prompt, prompt_input)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(
            lambda e: isinstance(e, HTTPException)
            and getattr(e, "status_code", 0) == 503
        ),
        reraise=True,
    )
    async def _generate_single_version(idx: int) -> dict:
        try:
            # 为避免并发使用同一个会话导致 Session is already flushing，
            # 每个并发任务使用独立的会话与服务实例
            async with AsyncSessionLocal() as local_session:
                local_llm_service = LLMService(local_session)
                response = await local_llm_service.get_llm_response(
                    system_prompt=writer_prompt,
                    conversation_history=[{"role": "user", "content": prompt_input}],
                    temperature=0.7,
                    user_id=current_user.id,
                    timeout=600.0,
                )
            cleaned = remove_think_tags(response)
            normalized = unwrap_markdown_json(cleaned)
            try:
                parsed = json.loads(normalized)
                parsed.setdefault("status", "success")
                return parsed
            except json.JSONDecodeError as parse_err:
                logger.warning(
                    "项目 %s 第 %s 章第 %s 个版本 JSON 解析失败，将原始内容作为纯文本处理: %s",
                    project_id,
                    request.chapter_number,
                    idx + 1,
                    parse_err,
                )
                return {"content": normalized, "status": "success"}
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(
                "项目 %s 生成第 %s 章第 %s 个版本时发生异常: %s",
                project_id,
                request.chapter_number,
                idx + 1,
                exc,
            )
            return {
                "content": f"生成失败: {exc}",
                "status": "failed",
                "error": str(exc),
            }

    version_count = await _resolve_version_count(session)
    logger.info(
        "项目 %s 第 %s 章计划生成 %s 个版本",
        project_id,
        request.chapter_number,
        version_count,
    )
    tasks = [_generate_single_version(idx) for idx in range(version_count)]
    raw_versions = await asyncio.gather(*tasks)
    contents: list[str] = []
    metadata: list[dict] = []
    for variant in raw_versions:
        if isinstance(variant, dict):
            # 事件驱动模式：提取 full_content 字段
            if "full_content" in variant and isinstance(variant["full_content"], str):
                contents.append(variant["full_content"])
            elif "content" in variant and isinstance(variant["content"], str):
                contents.append(variant["content"])
            elif "chapter_content" in variant:
                contents.append(str(variant["chapter_content"]))
            else:
                contents.append(json.dumps(variant, ensure_ascii=False))
            metadata.append(variant)
        else:
            contents.append(str(variant))
            metadata.append({"raw": variant})

    await novel_service.replace_chapter_versions(chapter, contents, metadata)

    # 事件驱动模式：更新事件进度
    # 从第一个版本的 metadata 中提取事件进度信息
    if metadata and isinstance(metadata[0], dict):
        first_version = metadata[0]
        event_progress_after = first_version.get(
            "event_progress_after", current_event.progress
        )
        completed_key_points_in_chapter = first_version.get(
            "completed_key_points_in_this_chapter", []
        )
        is_event_complete = first_version.get("is_event_complete", False)

        # 更新章节的事件进度
        await novel_service.update_chapter_event_progress(
            chapter=chapter,
            event_progress_after=event_progress_after,
            completed_key_points=completed_key_points_in_chapter,
            is_event_complete=is_event_complete,
        )

        # 如果事件完成，尝试切换到下一个事件
        if is_event_complete:
            next_event = await novel_service.check_and_switch_event(
                project_id, current_event.id
            )
            if next_event:
                logger.info(
                    f"事件 {current_event.event_id} 已完成，已切换到下一个事件 {next_event.event_id}"
                )
            else:
                logger.info(
                    f"事件 {current_event.event_id} 已完成，当前卷的所有事件已完成"
                )

    logger.info(
        "项目 %s 第 %s 章生成完成，已写入 %s 个版本",
        project_id,
        request.chapter_number,
        len(contents),
    )
    return await _load_project_schema(novel_service, project_id, current_user.id)


async def _resolve_version_count(session: AsyncSession) -> int:
    repo = SystemConfigRepository(session)
    record = await repo.get_by_key("writer.chapter_versions")
    if record:
        try:
            value = int(record.value)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    env_value = os.getenv("WRITER_CHAPTER_VERSION_COUNT")
    if env_value:
        try:
            value = int(env_value)
            if value > 0:
                return value
        except ValueError:
            pass
    return 3


@router.post("/novels/{project_id}/chapters/select", response_model=NovelProjectSchema)
async def select_chapter_version(
    project_id: str,
    request: SelectVersionRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    chapter = next(
        (ch for ch in project.chapters if ch.chapter_number == request.chapter_number),
        None,
    )
    if not chapter:
        logger.warning(
            "项目 %s 未找到第 %s 章，无法选择版本", project_id, request.chapter_number
        )
        raise HTTPException(status_code=404, detail="章节不存在")

    selected = await novel_service.select_chapter_version(
        chapter, request.version_index
    )
    logger.info(
        "用户 %s 选择了项目 %s 第 %s 章的第 %s 个版本",
        current_user.id,
        project_id,
        request.chapter_number,
        request.version_index,
    )
    if selected and selected.content:
        summary = await llm_service.get_summary(
            selected.content,
            temperature=0.15,
            user_id=current_user.id,
            timeout=180.0,
        )
        chapter.real_summary = remove_think_tags(summary)
        await session.commit()

        if settings.vector_store_enabled:
            # 后台任务内新建会话与服务，避免复用请求态资源
            async def ingest_chapter_background_task(
                project_id_: str, chapter_number_: int, user_id_: int
            ):
                try:
                    async with AsyncSessionLocal() as bg_session:
                        bg_llm_service = LLMService(bg_session)
                        try:
                            vector_store_local = VectorStoreService()
                        except RuntimeError as exc:
                            logger.warning("向量库初始化失败，跳过章节入库: %s", exc)
                            return
                        novel_service_local = NovelService(bg_session)
                        project_local = await novel_service_local.get_project(
                            project_id_
                        )
                        outline_local = next(
                            (
                                item
                                for item in project_local.outlines
                                if item.chapter_number == chapter_number_
                            ),
                            None,
                        )
                        chapter_title_local = (
                            outline_local.title
                            if outline_local and outline_local.title
                            else f"第{chapter_number_}章"
                        )
                        stmt = select(Chapter).where(
                            Chapter.project_id == project_id_,
                            Chapter.chapter_number == chapter_number_,
                        )
                        result = await bg_session.execute(stmt)
                        chapter_local = result.scalars().first()
                        if (
                            not chapter_local
                            or not chapter_local.selected_version
                            or not chapter_local.selected_version.content
                        ):
                            return
                        ingestion_service = ChapterIngestionService(
                            llm_service=bg_llm_service, vector_store=vector_store_local
                        )
                        await ingestion_service.ingest_chapter(
                            project_id=project_id_,
                            chapter_number=chapter_number_,
                            title=chapter_title_local,
                            content=chapter_local.selected_version.content,
                            summary=chapter_local.real_summary,
                            user_id=user_id_,
                        )
                        logger.info(
                            "项目 %s 第 %s 章已同步至向量库",
                            project_id_,
                            chapter_number_,
                        )
                except Exception as exc:
                    logger.exception(
                        "项目 %s 第 %s 章向量入库失败: %s",
                        project_id_,
                        chapter_number_,
                        exc,
                    )

            background_tasks.add_task(
                ingest_chapter_background_task,
                project_id,
                chapter.chapter_number,
                current_user.id,
            )

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post(
    "/novels/{project_id}/chapters/evaluate", response_model=NovelProjectSchema
)
async def evaluate_chapter(
    project_id: str,
    request: EvaluateChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    chapter = next(
        (ch for ch in project.chapters if ch.chapter_number == request.chapter_number),
        None,
    )
    if not chapter:
        logger.warning(
            "项目 %s 未找到第 %s 章，无法执行评估", project_id, request.chapter_number
        )
        raise HTTPException(status_code=404, detail="章节不存在")
    if not chapter.versions:
        logger.warning(
            "项目 %s 第 %s 章无可评估版本", project_id, request.chapter_number
        )
        raise HTTPException(status_code=400, detail="无可评估的章节版本")

    evaluator_prompt = await prompt_service.get_prompt("evaluation")
    if not evaluator_prompt:
        logger.error(
            "缺少评估提示词，项目 %s 第 %s 章评估失败",
            project_id,
            request.chapter_number,
        )
        raise HTTPException(
            status_code=500,
            detail="缺少评估提示词，请联系管理员配置 'evaluation' 提示词",
        )

    project_schema = await novel_service._serialize_project(project)
    blueprint_dict = project_schema.blueprint.model_dump()

    versions_to_evaluate = [
        {"version_id": idx + 1, "content": version.content}
        for idx, version in enumerate(
            sorted(chapter.versions, key=lambda item: item.created_at)
        )
    ]
    # print("blueprint_dict:",blueprint_dict)
    evaluator_payload = {
        "novel_blueprint": blueprint_dict,
        "content_to_evaluate": {
            "chapter_number": chapter.chapter_number,
            "versions": versions_to_evaluate,
        },
    }

    evaluation_raw = await llm_service.get_llm_response(
        system_prompt=evaluator_prompt,
        conversation_history=[
            {
                "role": "user",
                "content": json.dumps(evaluator_payload, ensure_ascii=False),
            }
        ],
        temperature=0.3,
        user_id=current_user.id,
        timeout=360.0,
    )
    evaluation_clean = remove_think_tags(evaluation_raw)
    await novel_service.add_chapter_evaluation(chapter, None, evaluation_clean)
    logger.info("项目 %s 第 %s 章评估完成", project_id, request.chapter_number)

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/delete", response_model=NovelProjectSchema)
async def delete_chapters(
    project_id: str,
    request: DeleteChapterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    if not request.chapter_numbers:
        logger.warning("项目 %s 删除章节时未提供章节号", project_id)
        raise HTTPException(status_code=400, detail="请提供要删除的章节号列表")
    novel_service = NovelService(session)
    LLMService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    logger.info(
        "用户 %s 删除项目 %s 的章节 %s",
        current_user.id,
        project_id,
        request.chapter_numbers,
    )
    await novel_service.delete_chapters(project_id, request.chapter_numbers)

    if settings.vector_store_enabled:

        async def delete_vectors_background_task(
            project_id_: str, chapter_numbers_: list[int]
        ):
            try:
                try:
                    vector_store_local = VectorStoreService()
                except RuntimeError as exc:
                    logger.warning("向量库初始化失败，跳过删除: %s", exc)
                    return
                await vector_store_local.delete_by_chapters(
                    project_id_, chapter_numbers_
                )
                logger.info(
                    "项目 %s 已从向量库移除章节 %s", project_id_, chapter_numbers_
                )
            except Exception as exc:
                logger.exception("项目 %s 向量删除失败: %s", project_id_, exc)

        background_tasks.add_task(
            delete_vectors_background_task, project_id, request.chapter_numbers
        )

    return await novel_service.get_project_schema(project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/edit", response_model=NovelProjectSchema)
async def edit_chapter(
    project_id: str,
    request: EditChapterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    chapter = next(
        (ch for ch in project.chapters if ch.chapter_number == request.chapter_number),
        None,
    )
    if not chapter or chapter.selected_version is None:
        logger.warning(
            "项目 %s 第 %s 章尚未生成或未选择版本，无法编辑",
            project_id,
            request.chapter_number,
        )
        raise HTTPException(status_code=404, detail="章节尚未生成或未选择版本")

    chapter.selected_version.content = request.content
    chapter.word_count = len(request.content)
    logger.info(
        "用户 %s 更新了项目 %s 第 %s 章内容",
        current_user.id,
        project_id,
        request.chapter_number,
    )

    if request.content.strip():
        summary = await llm_service.get_summary(
            request.content,
            temperature=0.15,
            user_id=current_user.id,
            timeout=180.0,
        )
        chapter.real_summary = remove_think_tags(summary)
    await session.commit()

    if (
        settings.vector_store_enabled
        and chapter.selected_version
        and chapter.selected_version.content
    ):
        # 后台任务内新建会话与服务，避免复用请求态资源
        async def reingest_chapter_background_task(
            project_id_: str, chapter_number_: int, user_id_: int
        ):
            try:
                async with AsyncSessionLocal() as bg_session:
                    bg_llm_service = LLMService(bg_session)
                    try:
                        vector_store_local = VectorStoreService()
                    except RuntimeError as exc:
                        logger.warning("向量库初始化失败，跳过章节重建: %s", exc)
                        return
                    # 取最新章节与标题
                    novel_service_local = NovelService(bg_session)
                    project_local = await novel_service_local.get_project(project_id_)
                    outline_local = next(
                        (
                            item
                            for item in project_local.outlines
                            if item.chapter_number == chapter_number_
                        ),
                        None,
                    )
                    chapter_title_local = (
                        outline_local.title
                        if outline_local and outline_local.title
                        else f"第{chapter_number_}章"
                    )
                    stmt = select(Chapter).where(
                        Chapter.project_id == project_id_,
                        Chapter.chapter_number == chapter_number_,
                    )
                    result = await bg_session.execute(stmt)
                    chapter_local = result.scalars().first()
                    if (
                        not chapter_local
                        or not chapter_local.selected_version
                        or not chapter_local.selected_version.content
                    ):
                        return
                    ingestion_service = ChapterIngestionService(
                        llm_service=bg_llm_service, vector_store=vector_store_local
                    )
                    await ingestion_service.ingest_chapter(
                        project_id=project_id_,
                        chapter_number=chapter_number_,
                        title=chapter_title_local,
                        content=chapter_local.selected_version.content,
                        summary=chapter_local.real_summary,
                        user_id=user_id_,
                    )
                    logger.info(
                        "项目 %s 第 %s 章更新内容已同步至向量库",
                        project_id_,
                        chapter_number_,
                    )
            except Exception as exc:
                logger.exception(
                    "项目 %s 第 %s 章向量更新失败: %s",
                    project_id_,
                    chapter_number_,
                    exc,
                )

        background_tasks.add_task(
            reingest_chapter_background_task,
            project_id,
            chapter.chapter_number,
            current_user.id,
        )

    return await novel_service.get_project_schema(project_id, current_user.id)


@router.post(
    "/novels/{project_id}/volumes/{volume_id}/check-completion",
    response_model=VolumeCompletionCheckResponse,
)
async def check_volume_completion(
    project_id: str,
    volume_id: int,
    request: VolumeCompletionCheckRequest = None,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> VolumeCompletionCheckResponse:
    """检查分卷完成度.

    基于分卷大纲的完成标准和已写章节内容,判断分卷是否已经完成
    如果未提供 completed_chapters,则自动从数据库获取该分卷的所有章节
    """
    novel_service = NovelService(session)
    rolling_service = RollingOutlineService(session)

    await novel_service.ensure_project_owner(project_id, current_user.id)
    logger.info(
        "用户 %s 检查项目 %s 第 %s 卷的完成度", current_user.id, project_id, volume_id
    )

    try:
        # 如果未提供 completed_chapters,从数据库获取
        if request is None or not request.completed_chapters:
            logger.info("未提供章节数据,从数据库获取分卷 %s 的章节", volume_id)

            # 获取分卷信息
            from sqlalchemy import select

            from ...models.novel import VolumeOutline

            stmt = select(VolumeOutline).where(
                VolumeOutline.id == volume_id, VolumeOutline.project_id == project_id
            )
            result_volume = await session.execute(stmt)
            volume = result_volume.scalar_one_or_none()

            if not volume:
                raise HTTPException(status_code=404, detail=f"未找到分卷 {volume_id}")

            # 获取该分卷范围内的所有章节
            completed_chapters = []
            if volume.actual_start_chapter and volume.actual_end_chapter:
                stmt = (
                    select(Chapter)
                    .where(
                        Chapter.project_id == project_id,
                        Chapter.chapter_number >= volume.actual_start_chapter,
                        Chapter.chapter_number <= volume.actual_end_chapter,
                    )
                    .order_by(Chapter.chapter_number)
                )
                result_chapters = await session.execute(stmt)
                chapters = result_chapters.scalars().all()

                completed_chapters = [
                    {
                        "chapter_number": ch.chapter_number,
                        "title": ch.title or f"第{ch.chapter_number}章",
                        "content": ch.actual_content or "",
                    }
                    for ch in chapters
                ]
                logger.info(f"从数据库获取到 {len(completed_chapters)} 个章节")
            else:
                logger.warning(f"分卷 {volume_id} 尚未设置实际章节范围")
                # 如果分卷还没有实际章节范围,返回空结果
                return VolumeCompletionCheckResponse(
                    is_completed=False,
                    completed_criteria=[],
                    remaining_criteria=volume.completion_criteria or [],
                    estimated_remaining_chapters=volume.estimated_chapters,
                    suggestion="该分卷尚未开始写作,无法检查完成度。请先生成章节内容。",
                )
        else:
            completed_chapters = request.completed_chapters

        # 调用分卷完成度检查服务
        result = await rolling_service.check_volume_completion(
            project_id=project_id,
            volume_id=volume_id,
            written_chapters=completed_chapters,
            user_id=current_user.id,
        )

        # 从 LLM 返回的结果中提取需要的字段
        completed_criteria = [
            item["criterion"]
            for item in result.get("criteria_status", [])
            if item.get("is_met")
        ]
        remaining_criteria = [
            item["criterion"]
            for item in result.get("criteria_status", [])
            if not item.get("is_met")
        ]

        return VolumeCompletionCheckResponse(
            is_completed=result.get("is_completed", False),
            completed_criteria=completed_criteria,
            remaining_criteria=remaining_criteria,
            estimated_remaining_chapters=None,  # TODO: 从 result 中提取
            suggestion=result.get("suggestion", ""),
        )
    except ValueError as e:
        logger.error("检查分卷完成度失败: %s", str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("检查分卷完成度时发生未知错误: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"检查失败: {str(e)}")
    except Exception as e:
        logger.exception("检查分卷完成度时发生错误")
        raise HTTPException(status_code=500, detail=f"检查失败: {str(e)}")


@router.post("/novels/{project_id}/volumes/generate-next")
async def generate_next_volume(
    project_id: str,
    request: GenerateNextVolumeRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """生成下一卷大纲.

    当前分卷完成后，基于总体框架和已完成分卷的实际发展，生成下一卷的大纲
    """
    from ..models.novel import VolumeOutline

    novel_service = NovelService(session)
    rolling_service = RollingOutlineService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    logger.info("用户 %s 为项目 %s 生成下一卷大纲", current_user.id, project_id)

    try:
        # 构建故事上下文
        blueprint = await novel_service._build_blueprint_schema(project)
        story_context = {
            "title": blueprint.title,
            "genre": blueprint.genre,
            "tone": blueprint.tone,
            "world_setting": blueprint.world_setting,
            "characters": [
                {
                    "name": char.get("name"),
                    "identity": char.get("identity"),
                    "personality": char.get("personality"),
                }
                for char in blueprint.characters[:5]  # 只传主要角色
            ],
        }

        # 调用生成下一卷大纲服务
        result = await rolling_service.generate_next_volume_outline(
            project_id=project_id,
            previous_volume_id=request.previous_volume_id,
            story_context=story_context,
            user_id=current_user.id,
        )

        # 保存生成的分卷大纲到数据库
        volume = VolumeOutline(
            project_id=project_id,
            volume_number=result["volume_number"],
            volume_title=result["volume_title"],
            arc_phase=result.get("arc_phase", "opening"),  # 新增：保存 arc_phase
            volume_goal=result["volume_goal"],
            estimated_chapters=result.get("estimated_chapters"),
            actual_start_chapter=None,  # 将在开始写作时填入
            actual_end_chapter=None,
            completion_criteria=result.get("completion_criteria", []),
            major_arcs=result.get("major_arcs", []),
            new_characters=result.get("new_characters", []),
            foreshadowing=result.get("foreshadowing", []),
            status="draft",
        )
        session.add(volume)
        await session.commit()
        await session.refresh(volume)

        logger.info(
            "项目 %s 第 %s 卷大纲已保存（ID: %s）",
            project_id,
            result["volume_number"],
            volume.id,
        )

        return {
            "success": True,
            "volume_id": volume.id,
            "volume_outline": result,
            "message": f"成功生成第 {result.get('volume_number')} 卷大纲",
        }
    except ValueError as e:
        logger.error("生成下一卷大纲失败: %s", str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("生成下一卷大纲时发生错误")
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")


# ------------------------------------------------------------------
# 事件管理 API
# ------------------------------------------------------------------


@router.post("/novels/{project_id}/events/generate")
async def generate_plot_events(
    project_id: str,
    volume_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """为指定卷生成情节事件。.

    Args:
        project_id: 项目ID
        volume_id: 卷ID
        session: 数据库会话
        current_user: 当前用户

    Returns:
        生成的事件列表

    """
    novel_service = NovelService(session)
    plot_event_service = PlotEventService(session)

    # 验证项目所有权
    await novel_service.ensure_project_owner(project_id, current_user.id)

    logger.info(
        f"用户 {current_user.id} 开始为项目 {project_id} 的卷 {volume_id} 生成情节事件"
    )

    try:
        # 调用 PlotEventService 生成事件
        events = await plot_event_service.generate_events_for_volume(
            project_id=project_id, volume_id=volume_id, user_id=current_user.id
        )

        logger.info(f"项目 {project_id} 的卷 {volume_id} 成功生成 {len(events)} 个事件")

        return {
            "success": True,
            "events": [
                {
                    "event_id": event.event_id,
                    "event_title": event.event_title,
                    "act": event.act,
                    "event_type": event.event_type,
                    "description": event.description,
                    "key_points": event.key_points,
                    "progress": event.progress,
                    "status": event.status,
                }
                for event in events
            ],
            "message": f"成功生成 {len(events)} 个情节事件",
        }
    except Exception as e:
        logger.exception(f"生成情节事件失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成情节事件失败: {str(e)}")


@router.get("/novels/{project_id}/events")
async def get_all_events(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """获取项目的所有事件。.

    Args:
        project_id: 项目ID
        session: 数据库会话
        current_user: 当前用户

    Returns:
        事件列表

    """
    novel_service = NovelService(session)
    plot_event_service = PlotEventService(session)

    # 验证项目所有权
    await novel_service.ensure_project_owner(project_id, current_user.id)

    events = await plot_event_service.get_events_by_project(project_id)

    return {
        "success": True,
        "events": [
            {
                "id": event.id,
                "event_id": event.event_id,
                "event_title": event.event_title,
                "act": event.act,
                "arc_index": event.arc_index,
                "event_type": event.event_type,
                "description": event.description,
                "key_points": event.key_points,
                "completed_key_points": event.completed_key_points,
                "progress": event.progress,
                "status": event.status,
                "volume_id": event.volume_id,
                "sequence": event.sequence,
            }
            for event in events
        ],
    }


@router.get("/novels/{project_id}/volumes/{volume_id}/events")
async def get_volume_events(
    project_id: str,
    volume_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """获取指定卷的所有事件。.

    Args:
        project_id: 项目ID
        volume_id: 卷ID
        session: 数据库会话
        current_user: 当前用户

    Returns:
        事件列表

    """
    novel_service = NovelService(session)
    plot_event_service = PlotEventService(session)

    # 验证项目所有权
    await novel_service.ensure_project_owner(project_id, current_user.id)

    events = await plot_event_service.get_events_by_volume(volume_id)

    return {
        "success": True,
        "events": [
            {
                "id": event.id,
                "event_id": event.event_id,
                "event_title": event.event_title,
                "act": event.act,
                "arc_index": event.arc_index,
                "event_type": event.event_type,
                "description": event.description,
                "key_points": event.key_points,
                "completed_key_points": event.completed_key_points,
                "progress": event.progress,
                "status": event.status,
                "sequence": event.sequence,
            }
            for event in events
        ],
    }


class UpdateEventProgressRequest(BaseModel):
    """更新事件进度的请求体."""

    progress: int = Field(..., ge=0, le=100, description="进度（0-100）")
    completed_key_points: list[str] | None = Field(
        None, description="已完成的关键点列表"
    )


@router.put("/novels/{project_id}/events/{event_id}/progress")
async def update_event_progress(
    project_id: str,
    event_id: int,
    request: UpdateEventProgressRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """更新事件进度。.

    Args:
        project_id: 项目ID
        event_id: 事件ID
        request: 请求体,包含 progress 和 completed_key_points
        session: 数据库会话
        current_user: 当前用户

    Returns:
        更新后的事件

    """
    novel_service = NovelService(session)
    plot_event_service = PlotEventService(session)

    # 验证项目所有权
    await novel_service.ensure_project_owner(project_id, current_user.id)

    try:
        event = await plot_event_service.update_event_progress(
            event_id=event_id,
            progress=request.progress,
            completed_key_points=request.completed_key_points,
        )

        if not event:
            raise HTTPException(status_code=404, detail="事件不存在")

        logger.info(f"事件 {event_id} 的进度已更新为 {request.progress}%")

        return {
            "success": True,
            "event": {
                "id": event.id,
                "event_id": event.event_id,
                "event_title": event.event_title,
                "progress": event.progress,
                "status": event.status,
                "completed_key_points": event.completed_key_points,
            },
            "message": f"事件进度已更新为 {request.progress}%",
        }
    except Exception as e:
        logger.exception(f"更新事件进度失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新事件进度失败: {str(e)}")
