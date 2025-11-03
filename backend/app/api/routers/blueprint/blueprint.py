"""
蓝图生成API路由
"""

import json
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ....db.session import get_session
from ....core.dependencies import get_current_user
from ....schemas.user import UserInDB
from ....services.blueprint import BlueprintService

router = APIRouter()


@router.post(
    "/generate",
    response_model=Dict[str, Any],
    summary="生成蓝图",
    description="基于对话历史生成小说蓝图"
)
async def generate_blueprint(
    *,
    db: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
    conversation_history: List[Dict[str, str]],
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    生成蓝图

    - **conversation_history**: 对话历史列表
    - **project_id**: 可选的项目ID
    """
    try:
        blueprint_service = BlueprintService(db)

        blueprint = await blueprint_service.generate_blueprint(
            conversation_history=conversation_history,
            project_id=project_id
        )

        return {
            "success": True,
            "data": blueprint,
            "message": "蓝图生成成功"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"蓝图生成失败: {str(e)}"
        )


@router.get(
    "/{project_id}/generate-stream",
    summary="生成蓝图（SSE流式）",
    description="使用Server-Sent Events实时推送蓝图生成进度"
)
async def generate_blueprint_stream(
    project_id: str,
    db: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> StreamingResponse:
    """
    SSE流式生成蓝图，实时推送进度

    事件类型：
    - progress: 进度更新 {"step": 1, "total": 7, "message": "...", "percentage": 14}
    - complete: 生成完成 {"blueprint": {...}}
    - error: 生成失败 {"error": "..."}
    """

    async def event_generator():
        try:
            from ....repositories.novel_repository import NovelRepository
            novel_repo = NovelRepository(db)
            project = await novel_repo.get_by_id(project_id)

            if not project:
                error_data = json.dumps({"error": "项目不存在"})
                yield f"event: error\ndata: {error_data}\n\n"
                return

            # 从 conversations 关系构建 conversation_history
            conversation_history = [
                {"role": conv.role, "content": conv.content}
                for conv in project.conversations
            ] if project.conversations else []

            progress_queue = []

            async def send_progress(step: int, total: int, message: str):
                progress_data = json.dumps({
                    "step": step,
                    "total": total,
                    "message": message,
                    "percentage": int((step / total) * 100)
                })
                progress_queue.append(f"event: progress\ndata: {progress_data}\n\n")

            blueprint_service = BlueprintService(db)

            import asyncio
            generation_task = asyncio.create_task(
                blueprint_service.generate_blueprint(
                    conversation_history=conversation_history,
                    project_id=project_id,
                    progress_callback=send_progress
                )
            )

            while not generation_task.done():
                await asyncio.sleep(0.1)
                while progress_queue:
                    yield progress_queue.pop(0)

            # 检查任务是否异常
            if generation_task.exception():
                raise generation_task.exception()

            blueprint = generation_task.result()

            complete_data = json.dumps({"blueprint": blueprint})
            yield f"event: complete\ndata: {complete_data}\n\n"

        except Exception as e:
            error_data = json.dumps({"error": str(e)})
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get(
    "/{project_id}",
    response_model=Dict[str, Any],
    summary="获取蓝图",
    description="获取已生成的小说蓝图"
)
async def get_blueprint(
    project_id: str,
    db: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, Any]:
    """获取蓝图，从关联表结构读取"""
    try:
        from ....repositories.novel_repository import NovelRepository
        novel_repo = NovelRepository(db)
        project = await novel_repo.get_by_id(project_id)

        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="项目不存在"
            )

        if not project.blueprint:
            return {
                "success": True,
                "data": {},
                "message": "蓝图尚未生成"
            }

        blueprint_data = {
            "title": project.blueprint.title,
            "target_audience": project.blueprint.target_audience,
            "genre": project.blueprint.genre,
            "style": project.blueprint.style,
            "tone": project.blueprint.tone,
            "one_sentence_summary": project.blueprint.one_sentence_summary,
            "full_synopsis": project.blueprint.full_synopsis,
            "world_setting": project.blueprint.world_setting,
            "characters": [
                {
                    "name": char.name,
                    "identity": char.identity,
                    "personality": char.personality,
                    "goals": char.goals,
                    "abilities": char.abilities,
                    "relationship_to_protagonist": char.relationship_to_protagonist,
                    "extra": char.extra,
                    "position": char.position
                }
                for char in project.characters
            ],
            "relationships": [
                {
                    "from": rel.character_from,
                    "to": rel.character_to,
                    "description": rel.description,
                    "position": rel.position
                }
                for rel in project.relationships_
            ],
            "chapter_outline": [
                {
                    "chapter_number": outline.chapter_number,
                    "title": outline.title,
                    "summary": outline.summary
                }
                for outline in project.outlines
            ]
        }

        return {
            "success": True,
            "data": blueprint_data,
            "message": "获取蓝图成功"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取蓝图失败: {str(e)}"
        )
