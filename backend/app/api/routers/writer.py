import json
import asyncio
import logging
import os
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, Body, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
)

from ...core.config import settings
from ...core.dependencies import get_current_user
from ...db.session import get_session, AsyncSessionLocal
from ...models.novel import Chapter, ChapterOutline
from ...schemas.novel import (
    DeleteChapterRequest,
    EditChapterRequest,
    EvaluateChapterRequest,
    GenerateChapterRequest,
    GenerateOutlineRequest,
    SplitChapterOutlineRequest,
    NovelProject as NovelProjectSchema,
    SelectVersionRequest,
    UpdateChapterOutlineRequest,
)
from ...schemas.user import UserInDB
from ...services.chapter_context_service import ChapterContextService
from ...services.chapter_ingest_service import ChapterIngestionService
from ...services.llm_service import LLMService
from ...services.novel_service import NovelService
from ...services.prompt_service import PromptService
from ...services.vector_store_service import VectorStoreService
from ...utils.json_utils import remove_think_tags, unwrap_markdown_json
from ...repositories.system_config_repository import SystemConfigRepository

router = APIRouter(prefix="/api/writer", tags=["Writer"])
logger = logging.getLogger(__name__)


async def _load_project_schema(service: NovelService, project_id: str, user_id: int) -> NovelProjectSchema:
    return await service.get_project_schema(project_id, user_id)


def _extract_tail_excerpt(text: Optional[str], limit: int = 500) -> str:
    """截取章节结尾文本，默认保留 500 字。"""
    if not text:
        return ""
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[-limit:]


@router.post("/novels/{project_id}/chapters/generate", response_model=NovelProjectSchema)
async def generate_chapter(
    project_id: str,
    request: GenerateChapterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    logger.info("用户 %s 开始为项目 %s 生成第 %s 章", current_user.id, project_id, request.chapter_number)
    outline = await novel_service.get_outline(project_id, request.chapter_number)
    if not outline:
        logger.warning("项目 %s 未找到第 %s 章纲要，生成流程终止", project_id, request.chapter_number)
        raise HTTPException(status_code=404, detail="蓝图中未找到对应章节纲要")

    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)
    chapter.real_summary = None
    chapter.selected_version_id = None
    chapter.status = "generating"
    await session.commit()

    outlines_map = {item.chapter_number: item for item in project.outlines}

    chapters_needing_summary = []
    completed_chapters = []
    latest_prev_number = -1
    previous_summary_text = ""
    previous_tail_excerpt = ""
    for existing in project.chapters:
        if existing.chapter_number >= request.chapter_number:
            continue
        if existing.selected_version is None or not existing.selected_version.content:
            continue
        if not existing.real_summary:
            chapters_needing_summary.append(existing)
        else:
            completed_chapters.append(
                {
                    "chapter_number": existing.chapter_number,
                    "title": outlines_map.get(existing.chapter_number).title if outlines_map.get(existing.chapter_number) else f"第{existing.chapter_number}章",
                    "summary": existing.real_summary,
                }
            )
            if existing.chapter_number > latest_prev_number:
                latest_prev_number = existing.chapter_number
                previous_summary_text = existing.real_summary or ""
                previous_tail_excerpt = _extract_tail_excerpt(existing.selected_version.content)

    if chapters_needing_summary:
        # 为避免复用请求级会话/服务，后台任务内部新建会话与服务并按ID重取数据
        chapter_ids = [ch.id for ch in chapters_needing_summary if getattr(ch, "id", None)]

        async def generate_missing_summaries_task(project_id_: str, chapter_ids_: List[int], user_id_: int):
            try:
                async with AsyncSessionLocal() as bg_session:
                    bg_llm_service = LLMService(bg_session)
                    for ch_id in chapter_ids_:
                        stmt = select(Chapter).where(Chapter.id == ch_id)
                        result = await bg_session.execute(stmt)
                        ch = result.scalars().first()
                        if not ch or not ch.selected_version or not ch.selected_version.content:
                            continue
                        summary = await bg_llm_service.get_summary(
                            ch.selected_version.content,
                            temperature=0.15,
                            user_id=user_id_,
                            timeout=180.0,
                        )
                        ch.real_summary = remove_think_tags(summary)
                        await bg_session.commit()
                        logger.info("后台生成项目 %s 第 %s 章摘要完成", project_id_, ch.chapter_number)
            except Exception as exc:
                logger.exception("后台生成摘要失败: %s", exc)

        background_tasks.add_task(generate_missing_summaries_task, project_id, chapter_ids, current_user.id)

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
        "chapter_outline",
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
        raise HTTPException(status_code=500, detail="缺少写作提示词")

    # 初始化向量检索服务，若未配置则自动降级为纯提示词生成
    vector_store: Optional[VectorStoreService]
    if not settings.vector_store_enabled:
        vector_store = None
    else:
        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，RAG 检索被禁用: %s", exc)
            vector_store = None
    context_service = ChapterContextService(llm_service=llm_service, vector_store=vector_store)

    outline_title = outline.title or f"第{outline.chapter_number}章"
    outline_summary = outline.summary or "暂无摘要"
    query_parts = [outline_title, outline_summary]
    if request.writing_notes:
        query_parts.append(request.writing_notes)
    rag_query = "\n".join(part for part in query_parts if part)
    rag_context = await context_service.retrieve_for_generation(
        project_id=project_id,
        query_text=rag_query or outline.title or outline.summary or "",
        user_id=current_user.id,
    )
    chunk_count = len(rag_context.chunks) if rag_context and rag_context.chunks else 0
    summary_count = len(rag_context.summaries) if rag_context and rag_context.summaries else 0
    logger.info(
        "项目 %s 第 %s 章检索到 %s 个剧情片段和 %s 条摘要",
        project_id,
        request.chapter_number,
        chunk_count,
        summary_count,
    )
    # print("rag_context:",rag_context)
    # 将蓝图、前情、RAG 检索结果拼装成结构化段落，供模型理解
    blueprint_text = json.dumps(blueprint_dict, ensure_ascii=False, indent=2)
    completed_lines = [
        f"- 第{item['chapter_number']}章 - {item['title']}:{item['summary']}"
        for item in completed_chapters
    ]
    previous_summary_text = previous_summary_text or "暂无可用摘要"
    previous_tail_excerpt = previous_tail_excerpt or "暂无上一章结尾内容"
    completed_section = "\n".join(completed_lines) if completed_lines else "暂无前情摘要"
    rag_chunks_text = "\n\n".join(rag_context.chunk_texts()) if rag_context.chunks else "未检索到章节片段"
    rag_summaries_text = "\n".join(rag_context.summary_lines()) if rag_context.summaries else "未检索到章节摘要"
    writing_notes = request.writing_notes or "无额外写作指令"

    prompt_sections = [
        ("[世界蓝图](JSON)", blueprint_text),
        # ("[前情摘要]", completed_section),
        ("[上一章摘要]", previous_summary_text),
        ("[上一章结尾]", previous_tail_excerpt),
        ("[检索到的剧情上下文](Markdown)", rag_chunks_text),
        ("[检索到的章节摘要]", rag_summaries_text),
        (
            "[当前章节目标]",
            f"标题：{outline_title}\n摘要：{outline_summary}\n写作要求：{writing_notes}",
        ),
    ]
    prompt_input = "\n\n".join(f"{title}\n{content}" for title, content in prompt_sections if content)
    logger.debug("章节写作提示词：%s\n%s", writer_prompt, prompt_input)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(lambda e: isinstance(e, HTTPException) and getattr(e, "status_code", 0) == 503),
        reraise=True,
    )
    async def _generate_single_version(idx: int) -> Dict:
        try:
            # 为避免并发使用同一个会话导致 Session is already flushing，
            # 每个并发任务使用独立的会话与服务实例
            async with AsyncSessionLocal() as local_session:
                local_llm_service = LLMService(local_session)
                response = await local_llm_service.get_llm_response(
                    system_prompt=writer_prompt,
                    conversation_history=[{"role": "user", "content": prompt_input}],
                    temperature=0.9,
                    user_id=current_user.id,
                    timeout=600.0,
                )
            cleaned = remove_think_tags(response)
            normalized = unwrap_markdown_json(cleaned)
            try:
                parsed = json.loads(normalized)
                parsed.setdefault("status", "success")
                return parsed
            except json.JSONDecodeError:
                return {"content": normalized, "status": "success"}
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
    contents: List[str] = []
    metadata: List[Dict] = []
    for variant in raw_versions:
        if isinstance(variant, dict):
            if "content" in variant and isinstance(variant["content"], str):
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
    chapter = next((ch for ch in project.chapters if ch.chapter_number == request.chapter_number), None)
    if not chapter:
        logger.warning("项目 %s 未找到第 %s 章，无法选择版本", project_id, request.chapter_number)
        raise HTTPException(status_code=404, detail="章节不存在")

    selected = await novel_service.select_chapter_version(chapter, request.version_index)
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

        vector_store: Optional[VectorStoreService]
        if not settings.vector_store_enabled:
            vector_store = None
        else:
            try:
                vector_store = VectorStoreService()
            except RuntimeError as exc:
                logger.warning("向量库初始化失败，跳过章节向量同步: %s", exc)
                vector_store = None

        if settings.vector_store_enabled:
            # 后台任务内新建会话与服务，避免复用请求态资源
            async def ingest_chapter_background_task(project_id_: str, chapter_number_: int, user_id_: int):
                try:
                    async with AsyncSessionLocal() as bg_session:
                        bg_llm_service = LLMService(bg_session)
                        try:
                            vector_store_local = VectorStoreService()
                        except RuntimeError as exc:
                            logger.warning("向量库初始化失败，跳过章节入库: %s", exc)
                            return
                        novel_service_local = NovelService(bg_session)
                        project_local = await novel_service_local.get_project(project_id_)
                        outline_local = next((item for item in project_local.outlines if item.chapter_number == chapter_number_), None)
                        chapter_title_local = outline_local.title if outline_local and outline_local.title else f"第{chapter_number_}章"
                        stmt = select(Chapter).where(Chapter.project_id == project_id_, Chapter.chapter_number == chapter_number_)
                        result = await bg_session.execute(stmt)
                        chapter_local = result.scalars().first()
                        if not chapter_local or not chapter_local.selected_version or not chapter_local.selected_version.content:
                            return
                        ingestion_service = ChapterIngestionService(llm_service=bg_llm_service, vector_store=vector_store_local)
                        await ingestion_service.ingest_chapter(
                            project_id=project_id_,
                            chapter_number=chapter_number_,
                            title=chapter_title_local,
                            content=chapter_local.selected_version.content,
                            summary=chapter_local.real_summary,
                            user_id=user_id_,
                        )
                        logger.info("项目 %s 第 %s 章已同步至向量库", project_id_, chapter_number_)
                except Exception as exc:
                    logger.exception("项目 %s 第 %s 章向量入库失败: %s", project_id_, chapter_number_, exc)

            background_tasks.add_task(ingest_chapter_background_task, project_id, chapter.chapter_number, current_user.id)

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/evaluate", response_model=NovelProjectSchema)
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
    chapter = next((ch for ch in project.chapters if ch.chapter_number == request.chapter_number), None)
    if not chapter:
        logger.warning("项目 %s 未找到第 %s 章，无法执行评估", project_id, request.chapter_number)
        raise HTTPException(status_code=404, detail="章节不存在")
    if not chapter.versions:
        logger.warning("项目 %s 第 %s 章无可评估版本", project_id, request.chapter_number)
        raise HTTPException(status_code=400, detail="无可评估的章节版本")

    evaluator_prompt = await prompt_service.get_prompt("evaluation")
    if not evaluator_prompt:
        logger.error("缺少评估提示词，项目 %s 第 %s 章评估失败", project_id, request.chapter_number)
        raise HTTPException(status_code=500, detail="缺少评估提示词")

    project_schema = await novel_service._serialize_project(project)
    blueprint_dict = project_schema.blueprint.model_dump()

    versions_to_evaluate = [
        {"version_id": idx + 1, "content": version.content}
        for idx, version in enumerate(sorted(chapter.versions, key=lambda item: item.created_at))
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
        conversation_history=[{"role": "user", "content": json.dumps(evaluator_payload, ensure_ascii=False)}],
        temperature=0.3,
        user_id=current_user.id,
        timeout=360.0,
    )
    evaluation_clean = remove_think_tags(evaluation_raw)
    await novel_service.add_chapter_evaluation(chapter, None, evaluation_clean)
    logger.info("项目 %s 第 %s 章评估完成", project_id, request.chapter_number)

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/outline", response_model=NovelProjectSchema)
async def generate_chapter_outline(
    project_id: str,
    request: GenerateOutlineRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    await novel_service.ensure_project_owner(project_id, current_user.id)
    logger.info(
        "用户 %s 请求生成项目 %s 的章节大纲，起始章节 %s，数量 %s",
        current_user.id,
        project_id,
        request.start_chapter,
        request.num_chapters,
    )
    outline_prompt = await prompt_service.get_prompt("outline")
    if not outline_prompt:
        logger.error("缺少大纲提示词，项目 %s 大纲生成失败", project_id)
        raise HTTPException(status_code=500, detail="缺少大纲提示词")

    project_schema = await novel_service.get_project_schema(project_id, current_user.id)
    blueprint_dict = project_schema.blueprint.model_dump()

    payload = {
        "novel_blueprint": blueprint_dict,
        "wait_to_generate": {
            "start_chapter": request.start_chapter,
            "num_chapters": request.num_chapters,
        },
    }

    response = await llm_service.get_llm_response(
        system_prompt=outline_prompt,
        conversation_history=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        temperature=0.7,
        user_id=current_user.id,
        timeout=360.0,
    )
    normalized = unwrap_markdown_json(remove_think_tags(response))
    try:
        data = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="章节大纲生成失败") from exc

    new_outlines = data.get("chapters", [])
    for item in new_outlines:
        stmt = (
            select(ChapterOutline)
            .where(
                ChapterOutline.project_id == project_id,
                ChapterOutline.chapter_number == item.get("chapter_number"),
            )
        )
        result = await session.execute(stmt)
        record = result.scalars().first()
        if record:
            record.title = item.get("title", record.title)
            record.summary = item.get("summary", record.summary)
        else:
            session.add(
                ChapterOutline(
                    project_id=project_id,
                    chapter_number=item.get("chapter_number"),
                    title=item.get("title", ""),
                    summary=item.get("summary"),
                )
            )
    await session.commit()
    logger.info("项目 %s 章节大纲生成完成", project_id)

    return await novel_service.get_project_schema(project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/split-outline", response_model=NovelProjectSchema)
async def split_chapter_outline(
    project_id: str,
    request: SplitChapterOutlineRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """将某一章的大纲拆分为多章，并进行必要的局部重编号与写入。"""
    if request.target_count is None or request.target_count < 2:
        raise HTTPException(status_code=400, detail="目标拆分数量必须大于等于 2")

    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    await novel_service.ensure_project_owner(project_id, current_user.id)

    # 蓝图上下文
    project_schema = await novel_service.get_project_schema(project_id, current_user.id)
    blueprint_dict = project_schema.blueprint.model_dump()

    # 源章节纲要
    src_stmt = (
        select(ChapterOutline)
        .where(
            ChapterOutline.project_id == project_id,
            ChapterOutline.chapter_number == request.source_chapter,
        )
    )
    src_result = await session.execute(src_stmt)
    src_outline = src_result.scalars().first()
    if not src_outline:
        raise HTTPException(status_code=404, detail="未找到要拆分的章节纲要")

    subsequent_chapters_stmt = (
        select(ChapterOutline)
        .where(
            ChapterOutline.project_id == project_id,
            ChapterOutline.chapter_number > request.source_chapter,
        )
        .order_by(ChapterOutline.chapter_number)
        .limit(10)
    )
    subsequent_result = await session.execute(subsequent_chapters_stmt)
    subsequent_outlines = subsequent_result.scalars().all()

    subsequent_constraints = [
        {
            "chapter_number": ch.chapter_number,
            "title": ch.title,
            "summary": ch.summary,
        }
        for ch in subsequent_outlines
    ]

    payload = {
        "novel_blueprint": blueprint_dict,
        "split": {
            "source_chapter": request.source_chapter,
            "target_count": request.target_count,
            "pacing": request.pacing,
            "constraints": request.constraints or {},
        },
        "source_outline": {
            "chapter_number": src_outline.chapter_number,
            "title": src_outline.title,
            "summary": src_outline.summary,
        },
        "subsequent_chapters": subsequent_constraints,
    }

    outline_prompt = await prompt_service.get_prompt("split_outline")
    if not outline_prompt:
        raise HTTPException(status_code=500, detail="缺少拆分大纲提示词")

    try:
        raw = await llm_service.get_llm_response(
            system_prompt=outline_prompt,
            conversation_history=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            temperature=0.6,
            user_id=current_user.id,
            timeout=360.0,
        )
        normalized = unwrap_markdown_json(remove_think_tags(raw))
        data = json.loads(normalized)
    except Exception as exc:
        logger.exception("章节拆分大纲生成失败: %s", exc)
        raise HTTPException(status_code=500, detail="章节拆分大纲生成失败")

    parts = data.get("chapters", []) if isinstance(data, dict) else []
    m = int(request.target_count)
    if not isinstance(parts, list):
        parts = []
    if len(parts) < m:
        parts.extend([
            {"title": f"第{request.source_chapter + i}章（拆分）", "summary": "待完善"}
            for i in range(len(parts), m)
        ])
    elif len(parts) > m:
        parts = parts[:m]

    # 计算需要顺延的章节编号（局部级联）
    existing_numbers: Set[int] = set()
    out_rows = (await session.execute(
        select(ChapterOutline.chapter_number).where(ChapterOutline.project_id == project_id)
    )).scalars().all()
    ch_rows = (await session.execute(
        select(Chapter.chapter_number).where(Chapter.project_id == project_id)
    )).scalars().all()
    for n in out_rows:
        if n is not None:
            existing_numbers.add(int(n))
    for n in ch_rows:
        if n is not None:
            existing_numbers.add(int(n))

    s = int(request.source_chapter)
    needed = m - 1
    to_shift: List[int] = []
    if needed > 0:
        free_needed = needed
        n = s + 1
        while free_needed > 0:
            if n in existing_numbers:
                to_shift.append(n)
            else:
                free_needed -= 1
            n += 1

    OFFSET = 100000
    if to_shift:
        # 临时上移，避免冲突
        await session.execute(
            update(ChapterOutline)
            .where(
                ChapterOutline.project_id == project_id,
                ChapterOutline.chapter_number.in_(to_shift),
            )
            .values(chapter_number=ChapterOutline.chapter_number + OFFSET)
        )
        await session.execute(
            update(Chapter)
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number.in_(to_shift),
            )
            .values(chapter_number=Chapter.chapter_number + OFFSET)
        )

        # 调整为目标编号（+needed）
        await session.execute(
            update(ChapterOutline)
            .where(
                ChapterOutline.project_id == project_id,
                ChapterOutline.chapter_number.in_([x + OFFSET for x in to_shift]),
            )
            .values(chapter_number=ChapterOutline.chapter_number - (OFFSET - needed))
        )
        await session.execute(
            update(Chapter)
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number.in_([x + OFFSET for x in to_shift]),
            )
            .values(chapter_number=Chapter.chapter_number - (OFFSET - needed))
        )

    # 写入/更新拆分后的大纲
    for idx in range(m):
        target_number = s + idx
        item = parts[idx] or {}
        title = str(item.get("title") or f"第{target_number}章")
        summary = str(item.get("summary") or "")

        stmt = (
            select(ChapterOutline)
            .where(
                ChapterOutline.project_id == project_id,
                ChapterOutline.chapter_number == target_number,
            )
        )
        result = await session.execute(stmt)
        record = result.scalars().first()
        if record:
            record.title = title
            record.summary = summary
        else:
            session.add(
                ChapterOutline(
                    project_id=project_id,
                    chapter_number=target_number,
                    title=title,
                    summary=summary,
                )
            )

    await session.commit()
    logger.info(
        "项目 %s 第 %s 章已拆分为 %s 章，并完成局部重编号",
        project_id,
        s,
        m,
    )

    return await novel_service.get_project_schema(project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/update-outline", response_model=NovelProjectSchema)
async def update_chapter_outline(
    project_id: str,
    request: UpdateChapterOutlineRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    logger.info(
        "用户 %s 更新项目 %s 第 %s 章大纲",
        current_user.id,
        project_id,
        request.chapter_number,
    )

    stmt = (
        select(ChapterOutline)
        .where(
            ChapterOutline.project_id == project_id,
            ChapterOutline.chapter_number == request.chapter_number,
        )
    )
    result = await session.execute(stmt)
    outline = result.scalars().first()
    if not outline:
        outline = ChapterOutline(
            project_id=project_id,
            chapter_number=request.chapter_number,
        )
        session.add(outline)

    outline.title = request.title
    outline.summary = request.summary
    await session.commit()
    logger.info("项目 %s 第 %s 章大纲已更新", project_id, request.chapter_number)

    return await novel_service.get_project_schema(project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/delete", response_model=NovelProjectSchema)
async def delete_chapters(
    project_id: str,
    request: DeleteChapterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    if not request.chapter_numbers:
        logger.warning("项目 %s 未提供要删除的章节号", project_id)
        raise HTTPException(status_code=400, detail="请提供要删除的章节号")
    novel_service = NovelService(session)
    llm_service = LLMService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    logger.info(
        "用户 %s 删除项目 %s 的章节 %s",
        current_user.id,
        project_id,
        request.chapter_numbers,
    )
    await novel_service.delete_chapters(project_id, request.chapter_numbers)

    vector_store: Optional[VectorStoreService]
    if not settings.vector_store_enabled:
        vector_store = None
    else:
        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，跳过章节向量删除: %s", exc)
            vector_store = None

    if settings.vector_store_enabled:
        async def delete_vectors_background_task(project_id_: str, chapter_numbers_: List[int]):
            try:
                try:
                    vector_store_local = VectorStoreService()
                except RuntimeError as exc:
                    logger.warning("向量库初始化失败，跳过删除: %s", exc)
                    return
                await vector_store_local.delete_by_chapters(project_id_, chapter_numbers_)
                logger.info("项目 %s 已从向量库移除章节 %s", project_id_, chapter_numbers_)
            except Exception as exc:
                logger.exception("项目 %s 向量删除失败: %s", project_id_, exc)

        background_tasks.add_task(delete_vectors_background_task, project_id, request.chapter_numbers)

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
    chapter = next((ch for ch in project.chapters if ch.chapter_number == request.chapter_number), None)
    if not chapter or chapter.selected_version is None:
        logger.warning("项目 %s 第 %s 章尚未生成或未选择版本，无法编辑", project_id, request.chapter_number)
        raise HTTPException(status_code=404, detail="章节尚未生成或未选择版本")

    chapter.selected_version.content = request.content
    chapter.word_count = len(request.content)
    logger.info("用户 %s 更新了项目 %s 第 %s 章内容", current_user.id, project_id, request.chapter_number)

    if request.content.strip():
        summary = await llm_service.get_summary(
            request.content,
            temperature=0.15,
            user_id=current_user.id,
            timeout=180.0,
        )
        chapter.real_summary = remove_think_tags(summary)
    await session.commit()

    vector_store: Optional[VectorStoreService]
    if not settings.vector_store_enabled:
        vector_store = None
    else:
        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，跳过章节向量更新: %s", exc)
            vector_store = None

    if settings.vector_store_enabled and chapter.selected_version and chapter.selected_version.content:
        # 后台任务内新建会话与服务，避免复用请求态资源
        async def reingest_chapter_background_task(project_id_: str, chapter_number_: int, user_id_: int):
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
                    outline_local = next((item for item in project_local.outlines if item.chapter_number == chapter_number_), None)
                    chapter_title_local = outline_local.title if outline_local and outline_local.title else f"第{chapter_number_}章"
                    stmt = select(Chapter).where(Chapter.project_id == project_id_, Chapter.chapter_number == chapter_number_)
                    result = await bg_session.execute(stmt)
                    chapter_local = result.scalars().first()
                    if not chapter_local or not chapter_local.selected_version or not chapter_local.selected_version.content:
                        return
                    ingestion_service = ChapterIngestionService(llm_service=bg_llm_service, vector_store=vector_store_local)
                    await ingestion_service.ingest_chapter(
                        project_id=project_id_,
                        chapter_number=chapter_number_,
                        title=chapter_title_local,
                        content=chapter_local.selected_version.content,
                        summary=chapter_local.real_summary,
                        user_id=user_id_,
                    )
                    logger.info("项目 %s 第 %s 章更新内容已同步至向量库", project_id_, chapter_number_)
            except Exception as exc:
                logger.exception("项目 %s 第 %s 章向量更新失败: %s", project_id_, chapter_number_, exc)

        background_tasks.add_task(reingest_chapter_background_task, project_id, chapter.chapter_number, current_user.id)

    return await novel_service.get_project_schema(project_id, current_user.id)
