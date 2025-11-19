from __future__ import annotations

"""
章节上下文组装服务：负责调用向量库检索上下文，并对结果做基础格式化。

所有关键步骤均包含中文注释，方便团队理解 RAG 流程。
"""

import logging
import time
from dataclasses import dataclass

from ..core.config import settings
from ..repositories.rag_metrics_repository import RAGMetricsRepository
from ..services.llm_service import LLMService
from .vector_store_service import RetrievedChunk, RetrievedSummary, VectorStoreService

logger = logging.getLogger(__name__)


@dataclass
class ChapterRAGContext:
    """封装检索得到的上下文结果。."""

    query: str
    chunks: list[RetrievedChunk]
    summaries: list[RetrievedSummary]

    def chunk_texts(self) -> list[str]:
        """将检索到的 chunk 转换成带序号的 Markdown 段落。."""
        lines = []
        for idx, chunk in enumerate(self.chunks, start=1):
            title = chunk.chapter_title or f"第{chunk.chapter_number}章"
            lines.append(f"### Chunk {idx}(来源：{title})\n{chunk.content.strip()}")
        return lines

    def summary_lines(self) -> list[str]:
        """整理章节摘要，方便直接插入 Prompt。."""
        lines = []
        for summary in self.summaries:
            lines.append(
                f"- 第{summary.chapter_number}章 - {summary.title}:{summary.summary.strip()}"
            )
        return lines


class ChapterContextService:
    """章节上下文服务，整合查询、格式化与容错逻辑。."""

    def __init__(
        self,
        *,
        llm_service: LLMService,
        vector_store: VectorStoreService | None = None,
    ) -> None:
        self._llm_service = llm_service
        self._vector_store = vector_store
        self._session = llm_service.session

    async def retrieve_for_generation(
        self,
        *,
        project_id: str,
        query_text: str,
        user_id: int,
        top_k_chunks: int | None = None,
        top_k_summaries: int | None = None,
    ) -> ChapterRAGContext:
        """根据章节摘要构造检索向量，并返回 RAG 上下文。."""
        query = self._normalize(query_text)
        if not settings.vector_store_enabled or not self._vector_store:
            logger.debug("向量库未启用或初始化失败，跳过检索: project=%s", project_id)
            return ChapterRAGContext(query=query, chunks=[], summaries=[])

        start = time.perf_counter()
        embedding_model = (
            None
            if settings.embedding_provider == "ollama"
            else settings.embedding_model
        )
        embedding = await self._llm_service.get_embedding(
            query, user_id=user_id, model=embedding_model
        )
        if not embedding:
            logger.warning(
                "检索查询向量生成失败: project=%s chapter_query=%s", project_id, query
            )
            ctx = ChapterRAGContext(query=query, chunks=[], summaries=[])
            # 记录一次空检索（无向量）
            await self._log_metrics(
                project_id,
                latency_ms=int((time.perf_counter() - start) * 1000),
                chunks=[],
                summaries=[],
            )
            return ctx

        chunks = await self._vector_store.query_chunks(
            project_id=project_id,
            embedding=embedding,
            top_k=top_k_chunks,
        )
        summaries = await self._vector_store.query_summaries(
            project_id=project_id,
            embedding=embedding,
            top_k=top_k_summaries,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "章节上下文检索完成: project=%s chunks=%d summaries=%d query_preview=%s",
            project_id,
            len(chunks),
            len(summaries),
            query[:80],
        )
        await self._log_metrics(
            project_id, latency_ms=latency_ms, chunks=chunks, summaries=summaries
        )
        return ChapterRAGContext(query=query, chunks=chunks, summaries=summaries)

    async def _log_metrics(
        self,
        project_id: str,
        *,
        latency_ms: int,
        chunks: list[RetrievedChunk],
        summaries: list[RetrievedSummary],
    ) -> None:
        """记录一次检索的指标：延迟、结果规模、重复片段率。."""
        try:
            repo = RAGMetricsRepository(self._session)
            duplicate_ratio = self._compute_duplicate_ratio(
                [c.content or "" for c in chunks]
            )
            provider = (
                getattr(self._vector_store, "_provider", "libsql")
                if self._vector_store
                else "none"
            )
            await repo.add(
                project_id=project_id,
                latency_ms=latency_ms,
                chunk_count=len(chunks),
                summary_count=len(summaries),
                duplicate_ratio=duplicate_ratio,
                provider=str(provider),
            )
        except Exception as exc:  # pragma: no cover - 记录失败不影响主流程
            logger.debug("记录 RAG 指标失败: %s", exc)

    @staticmethod
    def _norm_text(text: str) -> str:
        # 统一空白，去除多余空格与换行
        return "".join(text.split())

    @staticmethod
    def _shingles(text: str, k: int = 3) -> set[str]:
        # 基于字符的 k-gram，适配中文/英文混排，无需额外分词
        if not text:
            return set()
        if len(text) <= k:
            return {text}
        return {text[i : i + k] for i in range(0, len(text) - k + 1)}

    @classmethod
    def _jaccard_sim(cls, a: str, b: str, k: int = 3) -> float:
        sa = cls._shingles(cls._norm_text(a), k=k)
        sb = cls._shingles(cls._norm_text(b), k=k)
        if not sa and not sb:
            return 1.0
        if not sa or not sb:
            return 0.0
        inter = len(sa & sb)
        union = len(sa | sb)
        return inter / union if union > 0 else 0.0

    def _compute_duplicate_ratio(self, texts: list[str]) -> float:
        total = len(texts)
        if total <= 1:
            return 0.0
        threshold = settings.rag_duplicate_similarity_threshold
        representatives: list[str] = []
        dups = 0
        for t in texts:
            matched = False
            for rep in representatives:
                if self._jaccard_sim(t, rep, k=3) >= threshold:
                    matched = True
                    break
            if matched:
                dups += 1
            else:
                representatives.append(t)
        return dups / total

    @staticmethod
    def _normalize(text: str) -> str:
        """统一压缩空白字符，避免影响检索效果。."""
        return " ".join(text.split())


__all__ = [
    "ChapterContextService",
    "ChapterRAGContext",
]
