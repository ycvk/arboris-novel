from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models.novel import NovelProject
from ..repositories.rag_metrics_repository import RAGMetricsRepository
from ..schemas.admin import RAGProjectStat, RAGStatus
from .vector_store_service import VectorStoreService

logger = logging.getLogger(__name__)


class RAGStatusService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.vector_store = VectorStoreService()

    async def get_status(self, top_n_projects: int = 5) -> RAGStatus:
        enabled = settings.vector_store_enabled
        provider = getattr(settings, "vector_db_provider", "libsql")
        url = settings.vector_db_url
        prefix = getattr(settings, "qdrant_collection_prefix", None)
        embedding_model = settings.embedding_model
        embedding_dim = settings.embedding_model_vector_size

        totals = {"chunks": 0, "summaries": 0}
        top_projects: list[RAGProjectStat] = []

        if enabled:
            try:
                totals = await self.vector_store.count_totals()
            except Exception as exc:  # pragma: no cover - 统计失败不致命
                logger.warning("统计向量库总量失败: %s", exc)

            # 从业务库选出最近更新的项目 TOPN，再对每个项目统计向量数量
            # 这样避免在 Qdrant 上做 group-by
            try:
                result = await self.session.execute(
                    select(NovelProject.id, NovelProject.title)
                    .order_by(NovelProject.updated_at.desc())
                    .limit(top_n_projects)
                )
                rows = list(result.all())
                for pid, title in rows:
                    counts = await self.vector_store.count_by_project(pid)
                    if counts.get("chunks", 0) or counts.get("summaries", 0):
                        top_projects.append(
                            RAGProjectStat(
                                project_id=pid,
                                title=title,
                                chunks=counts.get("chunks", 0),
                                summaries=counts.get("summaries", 0),
                            )
                        )
            except Exception as exc:  # pragma: no cover
                logger.warning("统计项目向量规模失败: %s", exc)

        # 聚合近 7 天的检索质量与性能指标
        avg_latency_ms_7d = None
        empty_recall_rate_7d = None
        duplicate_chunk_rate_7d = None
        try:
            metrics_repo = RAGMetricsRepository(self.session)
            win = await metrics_repo.window_stats(days=7)
            avg_latency_ms_7d = win.get("avg_latency_ms")
            empty_recall_rate_7d = win.get("empty_rate")
            duplicate_chunk_rate_7d = win.get("duplicate_rate")
        except Exception as exc:  # pragma: no cover
            logger.debug("汇总 7 天 RAG 指标失败: %s", exc)

        return RAGStatus(
            enabled=enabled,
            provider=provider,
            url=url,
            collection_prefix=prefix,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
            top_k_chunks=settings.vector_top_k_chunks,
            top_k_summaries=settings.vector_top_k_summaries,
            chunk_size=settings.vector_chunk_size,
            chunk_overlap=settings.vector_chunk_overlap,
            total_chunks=int(totals.get("chunks", 0)),
            total_summaries=int(totals.get("summaries", 0)),
            top_projects=top_projects,
            avg_latency_ms_7d=avg_latency_ms_7d,
            empty_recall_rate_7d=empty_recall_rate_7d,
            duplicate_chunk_rate_7d=duplicate_chunk_rate_7d,
        )


__all__ = ["RAGStatusService"]
