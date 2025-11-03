"""
蓝图分阶段生成API路由
"""

import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.dependencies import get_current_user, get_session
from ....core.security import decode_access_token
from ....models.user import User as UserInDB
from ....repositories.user_repository import UserRepository
from ....services.blueprint.blueprint_service import BlueprintService
from ....services.blueprint.draft_service import DraftService
from ....services.novel_service import NovelService
from ....services.auth_service import AuthService
from ....schemas.blueprint_stage import (
    StageGenerationResponse,
    SaveDraftRequest,
    DraftResponse,
)
from ....schemas.user import UserInDB as UserInDBSchema

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_current_user_from_query(
    token: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
) -> UserInDBSchema:
    """
    从查询参数获取token并验证用户（用于SSE等无法使用请求头的场景）
    """
    if not token:
        raise HTTPException(status_code=401, detail="缺少认证token")

    try:
        payload = decode_access_token(token)
        username = payload["sub"]
        repo = UserRepository(session)
        user = await repo.get_by_username(username)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在或已被禁用")
        service = AuthService(session)
        schema = UserInDBSchema.model_validate(user)
        schema.must_change_password = service.requires_password_reset(user)
        return schema
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token验证失败: {str(e)}")
        raise HTTPException(status_code=401, detail="无效的认证token")


@router.post("/{project_id}/generate-stage/1")
async def generate_stage1(
    project_id: str,
    db: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> StageGenerationResponse:
    """
    生成阶段1：核心概念
    """
    logger.info(f"用户 {current_user.username} 请求生成阶段1", extra={"project_id": project_id})

    try:
        novel_service = NovelService(db)
        blueprint_service = BlueprintService(db)

        # 验证项目权限
        project = await novel_service.ensure_project_owner(project_id, current_user.id)

        # 获取对话历史
        conversation_records = await novel_service.list_conversations(project_id)
        # 转换为字典格式
        conversation_history = [
            {"role": record.role, "content": record.content}
            for record in conversation_records
        ]

        # 生成阶段1
        stage1_data = await blueprint_service.generate_stage1_concept(conversation_history)

        return StageGenerationResponse(
            stage=1,
            data=stage1_data,
            next_stage=2,
            ai_message="核心概念已生成！请确认或修改后继续。"
        )

    except Exception as e:
        logger.error(f"生成阶段1失败: {str(e)}", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")


class Stage2Request(BaseModel):
    stage1_data: Dict[str, Any]

@router.post("/{project_id}/generate-stage/2")
async def generate_stage2(
    project_id: str,
    request: Stage2Request,
    db: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> StageGenerationResponse:
    """
    生成阶段2：故事框架
    """
    logger.info(f"用户 {current_user.username} 请求生成阶段2", extra={"project_id": project_id})

    try:
        novel_service = NovelService(db)
        blueprint_service = BlueprintService(db)

        # 验证项目权限
        project = await novel_service.ensure_project_owner(project_id, current_user.id)

        # 获取对话历史
        conversation_records = await novel_service.list_conversations(project_id)
        # 转换为字典格式
        conversation_history = [
            {"role": record.role, "content": record.content}
            for record in conversation_records
        ]

        # 生成阶段2
        stage2_data = await blueprint_service.generate_stage2_framework(
            conversation_history,
            request.stage1_data
        )

        return StageGenerationResponse(
            stage=2,
            data=stage2_data,
            next_stage=3,
            ai_message="故事框架已生成！请确认或修改后继续。"
        )

    except Exception as e:
        logger.error(f"生成阶段2失败: {str(e)}", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")


class Stage3Request(BaseModel):
    stage1_data: Dict[str, Any]
    stage2_data: Dict[str, Any]

@router.post("/{project_id}/generate-stage/3")
async def generate_stage3(
    project_id: str,
    request: Stage3Request,
    db: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> StageGenerationResponse:
    """
    生成阶段3：角色设定
    """
    logger.info(f"用户 {current_user.username} 请求生成阶段3", extra={"project_id": project_id})

    try:
        novel_service = NovelService(db)
        blueprint_service = BlueprintService(db)

        # 验证项目权限
        project = await novel_service.ensure_project_owner(project_id, current_user.id)

        # 生成阶段3
        stage3_data = await blueprint_service.generate_stage3_characters(
            request.stage1_data,
            request.stage2_data
        )

        return StageGenerationResponse(
            stage=3,
            data=stage3_data,
            next_stage=4,
            ai_message="角色设定已生成！请确认或修改后继续。"
        )

    except Exception as e:
        logger.error(f"生成阶段3失败: {str(e)}", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")


@router.get("/{project_id}/generate-stage/4/stream")
async def generate_stage4_stream(
    project_id: str,
    db: AsyncSession = Depends(get_session),
    current_user: UserInDBSchema = Depends(get_current_user_from_query),
):
    """
    生成阶段4：章节规划（SSE流式）
    从草稿中读取前3个阶段的数据
    """
    logger.info(f"用户 {current_user.username} 请求生成阶段4（流式）", extra={"project_id": project_id})

    try:
        novel_service = NovelService(db)
        blueprint_service = BlueprintService(db)
        draft_service = DraftService(db)

        # 验证项目权限
        project = await novel_service.ensure_project_owner(project_id, current_user.id)

        # 从草稿中获取前3个阶段的数据
        draft = await draft_service.get_draft(project_id)

        if not draft:
            logger.error("草稿不存在", extra={"project_id": project_id})
            raise HTTPException(status_code=400, detail="草稿不存在，请先完成前3个阶段")

        # 验证前3个阶段的数据完整性
        missing_stages = []
        if not draft.stage1:
            missing_stages.append("阶段1")
        if not draft.stage2:
            missing_stages.append("阶段2")
        if not draft.stage3:
            missing_stages.append("阶段3")

        if missing_stages:
            error_msg = f"缺少以下阶段的数据：{', '.join(missing_stages)}。请先完成前3个阶段。"
            logger.error(error_msg, extra={"project_id": project_id})
            raise HTTPException(status_code=400, detail=error_msg)

        stage1_data = draft.stage1.model_dump()
        stage2_data = draft.stage2.model_dump()
        stage3_data = draft.stage3.model_dump()

        async def event_generator():
            """SSE事件生成器"""
            import json

            try:
                chapters = []
                chapter_events = []

                async def chapter_callback(chapter_num: int, total: int, chapter_data: Dict):
                    """章节生成回调 - 收集章节数据和事件"""
                    chapters.append(chapter_data)
                    # 保存事件数据，稍后在生成器中 yield
                    chapter_events.append({
                        "chapter_num": chapter_num,
                        "total": total,
                        "data": chapter_data
                    })

                # 生成阶段4
                stage4_data = await blueprint_service.generate_stage4_chapters(
                    stage1_data,
                    stage2_data,
                    stage3_data,
                    progress_callback=chapter_callback
                )

                # 推送所有章节事件
                for event in chapter_events:
                    yield f"event: chapter\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"

                # 推送完成事件
                yield f"event: complete\ndata: {json.dumps(stage4_data, ensure_ascii=False)}\n\n"

            except Exception as e:
                logger.error(f"生成阶段4失败: {str(e)}", extra={"project_id": project_id})
                yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成阶段4失败: {str(e)}", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")


@router.post("/{project_id}/draft")
async def save_draft(
    project_id: str,
    draft_data: SaveDraftRequest,
    db: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """保存蓝图草稿"""
    logger.info(f"用户 {current_user.username} 保存草稿 - project_id={project_id}, current_stage={draft_data.current_stage}")

    try:
        novel_service = NovelService(db)
        draft_service = DraftService(db)

        # 验证项目权限
        project = await novel_service.ensure_project_owner(project_id, current_user.id)

        # 保存草稿
        draft = await draft_service.save_draft(project_id, draft_data)

        return {"success": True, "draft": draft}

    except Exception as e:
        logger.error(f"保存草稿失败: {str(e)}", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@router.get("/{project_id}/draft")
async def get_draft(
    project_id: str,
    db: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> DraftResponse:
    """获取蓝图草稿"""
    logger.info(f"用户 {current_user.username} 获取草稿", extra={"project_id": project_id})

    try:
        novel_service = NovelService(db)
        draft_service = DraftService(db)

        # 验证项目权限
        project = await novel_service.ensure_project_owner(project_id, current_user.id)

        # 获取草稿
        draft = await draft_service.get_draft(project_id)

        return DraftResponse(
            exists=draft is not None,
            draft=draft
        )

    except Exception as e:
        logger.error(f"获取草稿失败: {str(e)}", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@router.delete("/{project_id}/draft")
async def delete_draft(
    project_id: str,
    db: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """删除蓝图草稿"""
    logger.info(f"用户 {current_user.username} 删除草稿", extra={"project_id": project_id})

    try:
        novel_service = NovelService(db)
        draft_service = DraftService(db)

        # 验证项目权限
        project = await novel_service.ensure_project_owner(project_id, current_user.id)

        # 删除草稿
        success = await draft_service.delete_draft(project_id)

        return {"success": success}

    except Exception as e:
        logger.error(f"删除草稿失败: {str(e)}", extra={"project_id": project_id})
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")

