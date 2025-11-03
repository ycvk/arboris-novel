"""
蓝图生成API路由模块
基于langGraph试点项目移植
"""

from fastapi import APIRouter
from .blueprint import router as blueprint_router
from .stage import router as stage_router

# 创建主路由
router = APIRouter(prefix="/api/blueprint", tags=["blueprint"])

# 包含原有的蓝图路由（去掉prefix，因为已经在主路由中设置）
router.include_router(blueprint_router, prefix="")

# 包含新的分阶段路由
router.include_router(stage_router, prefix="")

__all__ = ["router"]
