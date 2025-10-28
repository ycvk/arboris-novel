from fastapi import APIRouter

from . import admin, auth, llm_config, novels, updates, writer, blueprint

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(novels.router)
api_router.include_router(writer.router)
api_router.include_router(admin.router)
api_router.include_router(updates.router)
api_router.include_router(llm_config.router)
api_router.include_router(blueprint.router)
