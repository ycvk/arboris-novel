import json
import logging
from typing import Dict, List
from pydantic import ValidationError

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...schemas.novel import (
    Blueprint,
    BlueprintGenerationResponse,
    BlueprintPatch,
    Chapter as ChapterSchema,
    ConverseRequest,
    ConverseResponseV2,
    NovelProject as NovelProjectSchema,
    NovelProjectSummary,
    NovelSectionResponse,
    NovelSectionType,
)
from ...schemas.user import UserInDB
from ...services.llm_service import LLMService
from ...services.novel_service import NovelService
from ...services.prompt_service import PromptService
from ...utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json


def _as_list_str(val) -> List[str]:
    if not val:
        return []
    if isinstance(val, list):
        out: List[str] = []
        for x in val:
            if isinstance(x, str):
                out.append(x)
            elif isinstance(x, dict):
                label = x.get("label")
                if isinstance(label, str):
                    out.append(label)
        return out
    return []


def _normalize_concept_payload(parsed: dict, prev_state: dict | None = None) -> dict:
    """严格校验并规范为新协议结构（仅接受新协议）。"""
    if isinstance(parsed, dict):
        # 新协议直通
        required = {"message", "question_type", "blueprint_progress", "completion_percentage", "next_action"}
        if required.issubset(parsed.keys()):
            # 确保 options 为字符串数组或 null
            opts = parsed.get("options")
            if opts is not None:
                parsed["options"] = _as_list_str(opts) or None
            return parsed

    # 无效/用户回声等：直接视为协议不符
    raise ValueError("concept response does not conform to expected schema")


def _preview_text(text: str, limit: int = 1200) -> str:
    try:
        if not isinstance(text, str):
            text = str(text)
    except Exception:
        return "<unprintable>"
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def _preview_history(messages: List[Dict[str, str]], max_items: int = 8, content_limit: int = 400) -> List[Dict[str, str]]:
    if not isinstance(messages, list):
        return []
    tail = messages[-max_items:]
    out: List[Dict[str, str]] = []
    for m in tail:
        role = m.get("role", "")
        content = m.get("content", "")
        if not isinstance(content, str):
            try:
                content = str(content)
            except Exception:
                content = "<unprintable>"
        out.append({"role": role, "content": _preview_text(content, content_limit)})
    return out

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/novels", tags=["Novels"])

def _ensure_prompt(prompt: str | None, name: str) -> str:
    if not prompt:
        raise HTTPException(status_code=500, detail=f"未配置名为 {name} 的提示词，请联系管理员")
    return prompt


@router.post("", response_model=NovelProjectSchema, status_code=status.HTTP_201_CREATED)
async def create_novel(
    title: str = Body(...),
    initial_prompt: str = Body(...),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """为当前用户创建一个新的小说项目。"""
    novel_service = NovelService(session)
    project = await novel_service.create_project(current_user.id, title, initial_prompt)
    logger.info("用户 %s 创建项目 %s", current_user.id, project.id)
    return await novel_service.get_project_schema(project.id, current_user.id)


@router.get("", response_model=List[NovelProjectSummary])
async def list_novels(
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> List[NovelProjectSummary]:
    """列出用户的全部小说项目摘要信息。"""
    novel_service = NovelService(session)
    projects = await novel_service.list_projects_for_user(current_user.id)
    logger.info("用户 %s 获取项目列表，共 %s 个", current_user.id, len(projects))
    return projects


@router.get("/{project_id}", response_model=NovelProjectSchema)
async def get_novel(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    logger.info("用户 %s 查询项目 %s", current_user.id, project_id)
    return await novel_service.get_project_schema(project_id, current_user.id)


@router.get("/{project_id}/sections/{section}", response_model=NovelSectionResponse)
async def get_novel_section(
    project_id: str,
    section: NovelSectionType,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelSectionResponse:
    novel_service = NovelService(session)
    logger.info("用户 %s 获取项目 %s 的 %s 区段", current_user.id, project_id, section)
    return await novel_service.get_section_data(project_id, current_user.id, section)


@router.get("/{project_id}/chapters/{chapter_number}", response_model=ChapterSchema)
async def get_chapter(
    project_id: str,
    chapter_number: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ChapterSchema:
    novel_service = NovelService(session)
    logger.info("用户 %s 获取项目 %s 第 %s 章", current_user.id, project_id, chapter_number)
    return await novel_service.get_chapter_schema(project_id, current_user.id, chapter_number)


@router.delete("", status_code=status.HTTP_200_OK)
async def delete_novels(
    project_ids: List[str] = Body(...),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, str]:
    novel_service = NovelService(session)
    await novel_service.delete_projects(project_ids, current_user.id)
    logger.info("用户 %s 删除项目 %s", current_user.id, project_ids)
    return {"status": "success", "message": f"成功删除 {len(project_ids)} 个项目"}


@router.post("/{project_id}/concept/converse", response_model=ConverseResponseV2)
async def converse_with_concept(
    project_id: str,
    request: ConverseRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ConverseResponseV2:
    """与概念设计师（LLM）进行对话，引导蓝图筹备。"""
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    history_records = await novel_service.list_conversations(project_id)
    logger.info(
        "项目 %s 概念对话请求，用户 %s，历史记录 %s 条",
        project_id,
        current_user.id,
        len(history_records),
    )
    conversation_history = [
        {"role": record.role, "content": record.content}
        for record in history_records
    ]
    user_content = json.dumps(request.user_input, ensure_ascii=False)
    conversation_history.append({"role": "user", "content": user_content})

    system_prompt = _ensure_prompt(await prompt_service.get_prompt("concept"), "concept")

    # 关键日志：打印传入 LLM 的 prompt 与对话内容（做长度截断）
    logger.info(
        "Concept LLM request: prompt_len=%s prompt_preview=%s",
        len(system_prompt or ""),
        _preview_text(system_prompt or "", 800),
    )
    logger.info(
        "Concept LLM request: history_total=%s history_preview=%s",
        len(conversation_history),
        _preview_history(conversation_history, 8, 300),
    )

    llm_response = await llm_service.get_llm_response(
        system_prompt=system_prompt,
        conversation_history=conversation_history,
        temperature=0.8,
        user_id=current_user.id,
        timeout=300.0,
    )
    # 关键日志：打印 LLM 原始返回（截断）
    logger.info("Concept LLM raw_response: %s", _preview_text(llm_response, 1200))
    llm_response = remove_think_tags(llm_response)

    try:
        normalized = unwrap_markdown_json(llm_response)
        # 关键日志：打印归一化后的 JSON 字符串（截断）
        logger.info("Concept LLM normalized: %s", _preview_text(normalized, 1200))
        sanitized = sanitize_json_like_text(normalized)
        parsed = json.loads(sanitized)
    except json.JSONDecodeError as exc:
        logger.exception(
            "Failed to parse concept converse response: project_id=%s user_id=%s error=%s\nOriginal response: %s\nNormalized: %s\nSanitized: %s",
            project_id,
            current_user.id,
            exc,
            llm_response[:1000],
            normalized[:1000] if 'normalized' in locals() else "N/A",
            sanitized[:1000] if 'sanitized' in locals() else "N/A",
        )
        raise HTTPException(
            status_code=500,
            detail=f"概念对话失败，AI 返回的内容格式不正确。请重试或联系管理员。错误详情: {str(exc)}"
        ) from exc

    # 规范化为新协议结构（严格校验，仅接受新协议）
    try:
        normalized_dict = _normalize_concept_payload(parsed, request.conversation_state)
    except ValueError as exc:
        logger.error(
            "Concept response not conforming: project_id=%s user_id=%s payload_preview=%s",
            project_id,
            current_user.id,
            _preview_text(normalized, 800),
        )
        raise HTTPException(status_code=500, detail="AI 返回内容不符合协议，请重试") from exc
    assistant_json = json.dumps(normalized_dict, ensure_ascii=False)

    await novel_service.append_conversation(project_id, "user", user_content)
    await novel_service.append_conversation(project_id, "assistant", assistant_json)

    logger.info(
        "项目 %s 概念对话完成，completion=%s next_action=%s",
        project_id,
        normalized_dict.get("completion_percentage"),
        normalized_dict.get("next_action"),
    )

    try:
        return ConverseResponseV2(**normalized_dict)
    except ValidationError as exc:
        logger.exception(
            "Invalid concept response schema: project_id=%s user_id=%s payload=%s",
            project_id,
            current_user.id,
            normalized_dict,
        )
        raise HTTPException(status_code=500, detail="AI 返回内容结构不符合协议") from exc


@router.post("/{project_id}/concept/regenerate", response_model=ConverseResponseV2)
async def regenerate_concept_reply(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ConverseResponseV2:
    """重新生成上一次 AI 回复：删除最后一条 assistant 消息后，基于相同历史重试。"""
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    await novel_service.ensure_project_owner(project_id, current_user.id)

    # 构造新的历史（移除最后一条 assistant）
    history_records = await novel_service.list_conversations(project_id)
    if not history_records:
        raise HTTPException(status_code=400, detail="暂无可重试的对话")
    # 确保存在可删除的 assistant
    last_assistant = None
    for record in reversed(history_records):
        if record.role == "assistant":
            last_assistant = record
            break
    if not last_assistant:
        raise HTTPException(status_code=400, detail="当前无可重试的 AI 回复")

    # 生成用于 LLM 的历史：去掉最后一个 assistant
    trimmed_records = []
    removed_once = False
    for record in reversed(history_records):
        if not removed_once and record.role == "assistant":
            removed_once = True
            continue
        trimmed_records.append(record)
    trimmed_records.reverse()

    conversation_history = [{"role": r.role, "content": r.content} for r in trimmed_records]
    system_prompt = _ensure_prompt(await prompt_service.get_prompt("concept"), "concept")

    logger.info(
        "Concept Regenerate request: history_total=%s history_preview=%s",
        len(conversation_history),
        _preview_history(conversation_history, 8, 300),
    )

    llm_response = await llm_service.get_llm_response(
        system_prompt=system_prompt,
        conversation_history=conversation_history,
        temperature=0.8,
        user_id=current_user.id,
        timeout=300.0,
    )
    logger.info("Concept Regenerate raw_response: %s", _preview_text(llm_response, 1200))
    llm_response = remove_think_tags(llm_response)

    try:
        normalized = unwrap_markdown_json(llm_response)
        logger.info("Concept Regenerate normalized: %s", _preview_text(normalized, 1200))
        parsed = json.loads(normalized)
    except json.JSONDecodeError as exc:
        logger.exception(
            "Failed to parse concept regenerate response: project_id=%s user_id=%s normalized=%s",
            project_id,
            current_user.id,
            normalized,
        )
        raise HTTPException(status_code=500, detail="AI 返回内容不是有效的 JSON") from exc

    try:
        normalized_dict = _normalize_concept_payload(parsed, None)
    except ValueError as exc:
        logger.error(
            "Concept regenerate not conforming: project_id=%s user_id=%s payload_preview=%s",
            project_id,
            current_user.id,
            _preview_text(normalized, 800),
        )
        raise HTTPException(status_code=500, detail="AI 返回内容不符合协议，请重试") from exc

    # 用新的 assistant 回复替换最后一条 assistant
    await novel_service.pop_last_conversation(project_id, role="assistant")
    assistant_json = json.dumps(normalized_dict, ensure_ascii=False)
    await novel_service.append_conversation(project_id, "assistant", assistant_json)

    logger.info(
        "项目 %s 概念对话重试完成，completion=%s next_action=%s",
        project_id,
        normalized_dict.get("completion_percentage"),
        normalized_dict.get("next_action"),
    )

    try:
        return ConverseResponseV2(**normalized_dict)
    except ValidationError as exc:
        logger.exception(
            "Invalid concept regenerate schema: project_id=%s user_id=%s payload=%s",
            project_id,
            current_user.id,
            normalized_dict,
        )
        raise HTTPException(status_code=500, detail="AI 返回内容结构不符合协议") from exc


@router.post("/{project_id}/blueprint/generate", response_model=BlueprintGenerationResponse)
async def generate_blueprint(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> BlueprintGenerationResponse:
    """
    根据完整对话生成可执行的小说蓝图（7步分步流程）
    """
    from ...services.blueprint import BlueprintService

    novel_service = NovelService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    logger.info("项目 %s 开始生成蓝图（7步流程）", project_id)

    history_records = await novel_service.list_conversations(project_id)
    if not history_records:
        logger.warning("项目 %s 缺少对话历史，无法生成蓝图", project_id)
        raise HTTPException(status_code=400, detail="缺少对话历史，请先完成概念对话后再生成蓝图")

    formatted_history: List[Dict[str, str]] = []
    for record in history_records:
        role = record.role
        content = record.content
        if not role or not content:
            continue
        try:
            normalized = unwrap_markdown_json(content)
            data = json.loads(normalized)
            if role == "user":
                user_value = data.get("value", data)
                if isinstance(user_value, str):
                    formatted_history.append({"role": "user", "content": user_value})
            elif role == "assistant":
                message_v2 = data.get("message") if isinstance(data, dict) else None
                if isinstance(message_v2, str) and message_v2:
                    formatted_history.append({"role": "assistant", "content": message_v2})
        except (json.JSONDecodeError, AttributeError):
            continue

    if not formatted_history:
        logger.warning("项目 %s 对话历史格式异常，无法提取有效内容", project_id)
        raise HTTPException(
            status_code=400,
            detail="无法从历史对话中提取有效内容，请检查对话历史格式或重新进行概念对话"
        )

    blueprint_service = BlueprintService(session)
    blueprint_data = await blueprint_service.generate_blueprint(
        conversation_history=formatted_history,
        project_id=None  # 不在service内保存，由下面的replace_blueprint统一处理
    )

    # 规范化 relationships 字段名（兼容新旧prompt格式）
    if "relationships" in blueprint_data and isinstance(blueprint_data["relationships"], list):
        normalized_relationships = []
        for rel in blueprint_data["relationships"]:
            if isinstance(rel, dict):
                # 处理新格式（character_from/character_to）和旧格式（from/to）
                normalized_rel = {
                    "character_from": rel.get("character_from") or rel.get("from"),
                    "character_to": rel.get("character_to") or rel.get("to"),
                    "description": rel.get("description", "")
                }
                normalized_relationships.append(normalized_rel)
        blueprint_data["relationships"] = normalized_relationships

    blueprint = Blueprint(**blueprint_data)
    await novel_service.replace_blueprint(project_id, blueprint)
    if blueprint.title:
        project.title = blueprint.title
        project.status = "blueprint_ready"
        await session.commit()
        logger.info("项目 %s 更新标题为 %s，并标记为 blueprint_ready", project_id, blueprint.title)

    ai_message = (
        "太棒了！我已经根据我们的对话整理出完整的小说蓝图。请确认是否进入写作阶段，或提出修改意见。"
    )
    return BlueprintGenerationResponse(blueprint=blueprint, ai_message=ai_message)


@router.post("/{project_id}/blueprint/save", response_model=NovelProjectSchema)
async def save_blueprint(
    project_id: str,
    blueprint_data: Blueprint | None = Body(None),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """保存蓝图信息，可用于手动覆盖自动生成结果。"""
    novel_service = NovelService(session)
    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    if blueprint_data:
        await novel_service.replace_blueprint(project_id, blueprint_data)
        if blueprint_data.title:
            project.title = blueprint_data.title
            await session.commit()
        logger.info("项目 %s 手动保存蓝图", project_id)
    else:
        logger.warning("项目 %s 保存蓝图时未提供蓝图数据", project_id)
        raise HTTPException(status_code=400, detail="缺少蓝图数据，请提供有效的蓝图内容")

    return await novel_service.get_project_schema(project_id, current_user.id)


@router.patch("/{project_id}/blueprint", response_model=NovelProjectSchema)
async def patch_blueprint(
    project_id: str,
    payload: BlueprintPatch,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """局部更新蓝图字段，对世界观或角色做微调。"""
    novel_service = NovelService(session)
    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    update_data = payload.model_dump(exclude_unset=True)
    await novel_service.patch_blueprint(project_id, update_data)
    logger.info("项目 %s 局部更新蓝图字段：%s", project_id, list(update_data.keys()))
    return await novel_service.get_project_schema(project_id, current_user.id)
