from __future__ import annotations

"""
向量检索服务，封装章节内容的存储与查询。

支持两种提供方：
- libsql（本地文件/远程 libsql）
- Qdrant（推荐，HNSW 近似检索，更适合规模化）

本文件中的注释均使用中文，便于团队成员快速理解 RAG 相关逻辑。
"""

import json
import logging
import math
from array import array
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.config import settings

try:  # noqa: SIM105 - 明确区分依赖缺失的情况
    import libsql_client
except ImportError:  # pragma: no cover - 在未安装依赖时提供友好提示
    libsql_client = None  # type: ignore[assignment]

try:  # Qdrant 可选依赖
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchAny,
        MatchValue,
        PointStruct,
        VectorParams,
    )
except Exception:  # pragma: no cover - 未安装时允许退化
    QdrantClient = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """向量检索得到的剧情片段。."""

    content: str
    chapter_number: int
    chapter_title: str | None
    score: float
    metadata: dict[str, Any]


@dataclass
class RetrievedSummary:
    """向量检索得到的章节摘要。."""

    chapter_number: int
    title: str
    summary: str
    score: float


class VectorStoreService:
    """向量库操作工具，确保不同小说项目的数据隔离。."""

    def __init__(self) -> None:
        if not settings.vector_store_enabled:
            logger.warning("未开启向量库配置，RAG 检索将被跳过。")
            self._provider = "none"
            self._client = None
            self._schema_ready = True
            return

        provider = (settings.vector_db_provider or "libsql").lower()
        # 兼容性处理：若显式指定 qdrant 但 URL 为 file:，则回退至 libsql
        url_detect = settings.vector_db_url or ""
        if provider == "qdrant" and url_detect.startswith("file:"):
            logger.warning(
                "VECTOR_DB_URL=%s 与 Qdrant 提供方不匹配，回退为 libsql。", url_detect
            )
            provider = "libsql"
        self._provider = provider

        if provider == "qdrant":
            if QdrantClient is None:  # pragma: no cover
                raise RuntimeError("缺少 qdrant-client 依赖，请先在环境中安装。")
            base_url = settings.vector_db_url
            logger.info("初始化 Qdrant 客户端: url=%s", base_url)
            self._client = QdrantClient(
                url=base_url, api_key=settings.vector_db_auth_token
            )
            self._schema_ready = False
            self._qdrant_chunks = f"{settings.qdrant_collection_prefix}_chunks"
            self._qdrant_summaries = f"{settings.qdrant_collection_prefix}_summaries"
            return

        # 默认使用 libsql
        if libsql_client is None:  # pragma: no cover - 运行环境缺少依赖
            raise RuntimeError("缺少 libsql-client 依赖，请先在环境中安装。")

        url = settings.vector_db_url
        if url and url.startswith("file:"):
            path_part = url.split("file:", 1)[1]
            resolved = Path(path_part).expanduser().resolve()
            resolved.parent.mkdir(parents=True, exist_ok=True)
            url = f"file:{resolved}"
            logger.info("向量库使用本地文件: %s", resolved)

        try:
            logger.info("初始化 libsql 客户端: url=%s", url)
            self._client = libsql_client.create_client(
                url=url,
                auth_token=settings.vector_db_auth_token,
            )
        except Exception as exc:  # pragma: no cover - 连接异常仅打印日志
            logger.error("初始化 libsql 客户端失败: %s", exc)
            self._client = None
            self._schema_ready = True
        else:
            self._schema_ready = False
            logger.info("libsql 客户端初始化成功，等待建表。")

    async def ensure_schema(self) -> None:
        """初始化向量表结构，保证系统首次运行即可使用。."""
        if not self._client or self._schema_ready:
            return

        if self._provider == "qdrant":
            # Qdrant 集合将在首次 upsert 时依据向量维度创建，这里仅检测是否存活
            try:
                # 轻量探活：尝试列出集合（失败也不致命）
                _ = self._client.get_collections()  # type: ignore[attr-defined]
            except Exception as exc:  # pragma: no cover
                logger.warning("Qdrant 探活失败: %s", exc)
            # 置为 True，避免重复尝试
            self._schema_ready = True
            return

        statements = [
            """
            CREATE TABLE IF NOT EXISTS rag_chunks (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                chapter_number INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                chapter_title TEXT,
                content TEXT NOT NULL,
                embedding BLOB NOT NULL,
                metadata TEXT,
                created_at INTEGER DEFAULT (unixepoch())
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_rag_chunks_project
            ON rag_chunks(project_id, chapter_number)
            """,
            """
            CREATE TABLE IF NOT EXISTS rag_summaries (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                chapter_number INTEGER NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                embedding BLOB NOT NULL,
                created_at INTEGER DEFAULT (unixepoch())
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_rag_summaries_project
            ON rag_summaries(project_id, chapter_number)
            """,
        ]

        try:
            for sql in statements:
                await self._client.execute(sql)  # type: ignore[union-attr]
            logger.info("已确保向量库表结构存在。")
        except Exception as exc:  # pragma: no cover - 初始化失败时记录日志
            logger.error("创建向量库表结构失败: %s", exc)
        else:
            self._schema_ready = True

    async def query_chunks(
        self,
        *,
        project_id: str,
        embedding: Sequence[float],
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """根据查询向量检索剧情片段，结果已按相似度排序。."""
        if not self._client or not embedding:
            return []

        await self.ensure_schema()
        top_k = top_k or settings.vector_top_k_chunks
        if top_k <= 0:
            return []

        if self._provider == "qdrant":
            try:
                flt = Filter(
                    must=[
                        FieldCondition(
                            key="project_id", match=MatchValue(value=project_id)
                        )
                    ]
                )
                results = self._client.search(
                    collection_name=self._qdrant_chunks,  # type: ignore[attr-defined]
                    query_vector=list(embedding),
                    limit=top_k,
                    query_filter=flt,
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("Qdrant 检索剧情片段失败: %s", exc)
                return []
            items: list[RetrievedChunk] = []
            for sp in results:
                payload = sp.payload or {}
                items.append(
                    RetrievedChunk(
                        content=payload.get("content", ""),
                        chapter_number=int(payload.get("chapter_number", 0)),
                        chapter_title=payload.get("chapter_title"),
                        score=float(sp.score or 0.0),
                        metadata=self._parse_metadata(payload.get("metadata")),
                    )
                )
            return items

        # libsql 分支
        blob = self._to_f32_blob(embedding)
        sql = """
        SELECT
            content,
            chapter_number,
            chapter_title,
            COALESCE(metadata, '{}') AS metadata,
            vector_distance_cosine(embedding, :query) AS distance
        FROM rag_chunks
        WHERE project_id = :project_id
        ORDER BY distance ASC
        LIMIT :limit
        """
        try:
            result = await self._client.execute(  # type: ignore[union-attr]
                sql,
                {
                    "project_id": project_id,
                    "query": blob,
                    "limit": top_k,
                },
            )
        except Exception as exc:  # pragma: no cover - 查询异常时仅记录
            if "no such function: vector_distance_cosine" in str(exc).lower():
                logger.warning(
                    "向量库缺少 vector_distance_cosine 函数，回退至应用层相似度计算。"
                )
                return await self._query_chunks_with_python_similarity(
                    project_id=project_id,
                    embedding=embedding,
                    top_k=top_k,
                )
            logger.warning("向量检索剧情片段失败: %s", exc)
            return []

        items: list[RetrievedChunk] = []
        for row in self._iter_rows(result):
            items.append(
                RetrievedChunk(
                    content=row.get("content", ""),
                    chapter_number=row.get("chapter_number", 0),
                    chapter_title=row.get("chapter_title"),
                    score=row.get("distance", 0.0),
                    metadata=self._parse_metadata(row.get("metadata")),
                )
            )
        return items

    async def query_summaries(
        self,
        *,
        project_id: str,
        embedding: Sequence[float],
        top_k: int | None = None,
    ) -> list[RetrievedSummary]:
        """根据查询向量检索章节摘要列表。."""
        if not self._client or not embedding:
            return []

        await self.ensure_schema()
        top_k = top_k or settings.vector_top_k_summaries
        if top_k <= 0:
            return []

        if self._provider == "qdrant":
            try:
                flt = Filter(
                    must=[
                        FieldCondition(
                            key="project_id", match=MatchValue(value=project_id)
                        )
                    ]
                )
                results = self._client.search(
                    collection_name=self._qdrant_summaries,  # type: ignore[attr-defined]
                    query_vector=list(embedding),
                    limit=top_k,
                    query_filter=flt,
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("Qdrant 检索章节摘要失败: %s", exc)
                return []
            items: list[RetrievedSummary] = []
            for sp in results:
                payload = sp.payload or {}
                items.append(
                    RetrievedSummary(
                        chapter_number=int(payload.get("chapter_number", 0)),
                        title=payload.get("title", ""),
                        summary=payload.get("summary", ""),
                        score=float(sp.score or 0.0),
                    )
                )
            return items

        blob = self._to_f32_blob(embedding)
        sql = """
        SELECT
            chapter_number,
            title,
            summary,
            vector_distance_cosine(embedding, :query) AS distance
        FROM rag_summaries
        WHERE project_id = :project_id
        ORDER BY distance ASC
        LIMIT :limit
        """
        try:
            result = await self._client.execute(  # type: ignore[union-attr]
                sql,
                {
                    "project_id": project_id,
                    "query": blob,
                    "limit": top_k,
                },
            )
        except Exception as exc:  # pragma: no cover - 查询异常时仅记录
            if "no such function: vector_distance_cosine" in str(exc).lower():
                logger.warning(
                    "向量库缺少 vector_distance_cosine 函数，回退至应用层相似度计算。"
                )
                return await self._query_summaries_with_python_similarity(
                    project_id=project_id,
                    embedding=embedding,
                    top_k=top_k,
                )
            logger.warning("向量检索章节摘要失败: %s", exc)
            return []

        items: list[RetrievedSummary] = []
        for row in self._iter_rows(result):
            items.append(
                RetrievedSummary(
                    chapter_number=row.get("chapter_number", 0),
                    title=row.get("title", ""),
                    summary=row.get("summary", ""),
                    score=row.get("distance", 0.0),
                )
            )
        return items

    async def upsert_chunks(
        self,
        *,
        records: Iterable[dict[str, Any]],
    ) -> None:
        """批量写入章节片段，供后续检索使用。."""
        if not self._client:
            return

        await self.ensure_schema()

        if self._provider == "qdrant":
            items = list(records)
            if not items:
                return
            dim = len(items[0].get("embedding", []) or [])
            if dim <= 0:
                return
            await self._ensure_qdrant_collection(self._qdrant_chunks, dim)  # type: ignore[attr-defined]
            points = []
            for item in items:
                emb = item.get("embedding", [])
                if not emb:
                    continue
                pid = self._stable_int_id(item.get("id", ""))
                payload = {
                    "id": item.get("id"),
                    "project_id": item.get("project_id"),
                    "chapter_number": item.get("chapter_number"),
                    "chunk_index": item.get("chunk_index"),
                    "chapter_title": item.get("chapter_title"),
                    "content": item.get("content"),
                    "metadata": item.get("metadata") or {},
                }
                points.append(PointStruct(id=pid, vector=list(emb), payload=payload))
            if points:
                try:
                    self._client.upsert(
                        collection_name=self._qdrant_chunks, points=points
                    )  # type: ignore[attr-defined]
                    logger.debug("Qdrant 已写入章节片段: count=%d", len(points))
                except Exception as exc:  # pragma: no cover
                    logger.error("Qdrant 写入 rag_chunks 失败: %s", exc)
            return

        # libsql 分支
        sql = """
        INSERT INTO rag_chunks (
            id,
            project_id,
            chapter_number,
            chunk_index,
            chapter_title,
            content,
            embedding,
            metadata
        ) VALUES (
            :id,
            :project_id,
            :chapter_number,
            :chunk_index,
            :chapter_title,
            :content,
            :embedding,
            :metadata
        )
        ON CONFLICT(id) DO UPDATE SET
            content=excluded.content,
            embedding=excluded.embedding,
            metadata=excluded.metadata,
            chapter_title=excluded.chapter_title
        """
        payload = []
        for item in records:
            embedding = item.get("embedding", [])
            payload.append(
                {
                    **item,
                    "embedding": self._to_f32_blob(embedding),
                    "metadata": json.dumps(
                        item.get("metadata") or {}, ensure_ascii=False
                    ),
                }
            )

        if not payload:
            return

        for item in payload:
            try:
                await self._client.execute(sql, item)  # type: ignore[union-attr]
            except Exception as exc:  # pragma: no cover - 单条写入失败时记录日志
                logger.error("写入 rag_chunks 失败: %s", exc)
            else:
                logger.debug(
                    "已写入章节片段: project=%s chapter=%s chunk=%s",
                    item.get("project_id"),
                    item.get("chapter_number"),
                    item.get("chunk_index"),
                )

    async def upsert_summaries(
        self,
        *,
        records: Iterable[dict[str, Any]],
    ) -> None:
        """同步章节摘要向量，供摘要层检索使用。."""
        if not self._client:
            return

        await self.ensure_schema()

        if self._provider == "qdrant":
            items = list(records)
            if not items:
                return
            dim = len(items[0].get("embedding", []) or [])
            if dim <= 0:
                return
            await self._ensure_qdrant_collection(self._qdrant_summaries, dim)  # type: ignore[attr-defined]
            points = []
            for item in items:
                emb = item.get("embedding", [])
                if not emb:
                    continue
                pid = self._stable_int_id(item.get("id", ""))
                payload = {
                    "id": item.get("id"),
                    "project_id": item.get("project_id"),
                    "chapter_number": item.get("chapter_number"),
                    "title": item.get("title"),
                    "summary": item.get("summary"),
                }
                points.append(PointStruct(id=pid, vector=list(emb), payload=payload))
            if points:
                try:
                    self._client.upsert(
                        collection_name=self._qdrant_summaries, points=points
                    )  # type: ignore[attr-defined]
                    logger.debug("Qdrant 已写入章节摘要: count=%d", len(points))
                except Exception as exc:  # pragma: no cover
                    logger.error("Qdrant 写入 rag_summaries 失败: %s", exc)
            return

        # libsql 分支
        sql = """
        INSERT INTO rag_summaries (
            id,
            project_id,
            chapter_number,
            title,
            summary,
            embedding
        ) VALUES (
            :id,
            :project_id,
            :chapter_number,
            :title,
            :summary,
            :embedding
        )
        ON CONFLICT(id) DO UPDATE SET
            summary=excluded.summary,
            embedding=excluded.embedding,
            title=excluded.title
        """

        payload = []
        for item in records:
            embedding = item.get("embedding", [])
            payload.append(
                {
                    **item,
                    "embedding": self._to_f32_blob(embedding),
                }
            )

        if not payload:
            return

        for item in payload:
            try:
                await self._client.execute(sql, item)  # type: ignore[union-attr]
            except Exception as exc:  # pragma: no cover - 单条写入失败时记录日志
                logger.error("写入 rag_summaries 失败: %s", exc)
            else:
                logger.debug(
                    "已写入章节摘要: project=%s chapter=%s",
                    item.get("project_id"),
                    item.get("chapter_number"),
                )

    # -------------------- 统计接口（用于 /admin RAG 状态） --------------------
    async def count_totals(self) -> dict[str, int]:
        """统计全局 chunks/summaries 数量。."""
        if not self._client:
            return {"chunks": 0, "summaries": 0}
        await self.ensure_schema()
        if self._provider == "qdrant":
            try:
                c1 = self._client.count(self._qdrant_chunks, exact=True).count  # type: ignore[attr-defined]
            except Exception:
                c1 = 0
            try:
                c2 = self._client.count(self._qdrant_summaries, exact=True).count  # type: ignore[attr-defined]
            except Exception:
                c2 = 0
            return {"chunks": int(c1 or 0), "summaries": int(c2 or 0)}

        # libsql 分支
        sql1 = "SELECT COUNT(1) AS c FROM rag_chunks"
        sql2 = "SELECT COUNT(1) AS c FROM rag_summaries"
        chunks = 0
        summaries = 0
        try:
            r1 = await self._client.execute(sql1)  # type: ignore[union-attr]
            rows = self._iter_rows(r1)
            if rows:
                chunks = int(list(rows)[0].get("c", 0))
        except Exception:
            chunks = 0
        try:
            r2 = await self._client.execute(sql2)  # type: ignore[union-attr]
            rows = self._iter_rows(r2)
            if rows:
                summaries = int(list(rows)[0].get("c", 0))
        except Exception:
            summaries = 0
        return {"chunks": chunks, "summaries": summaries}

    async def count_by_project(self, project_id: str) -> dict[str, int]:
        """统计指定项目的 chunks/summaries 数量。."""
        if not self._client:
            return {"chunks": 0, "summaries": 0}
        await self.ensure_schema()
        if self._provider == "qdrant":
            flt = Filter(
                must=[
                    FieldCondition(key="project_id", match=MatchValue(value=project_id))
                ]
            )
            try:
                c1 = self._client.count(
                    self._qdrant_chunks, count_filter=flt, exact=True
                ).count  # type: ignore[attr-defined]
            except Exception:
                c1 = 0
            try:
                c2 = self._client.count(
                    self._qdrant_summaries, count_filter=flt, exact=True
                ).count  # type: ignore[attr-defined]
            except Exception:
                c2 = 0
            return {"chunks": int(c1 or 0), "summaries": int(c2 or 0)}

        # libsql 分支
        sql1 = "SELECT COUNT(1) AS c FROM rag_chunks WHERE project_id = :pid"
        sql2 = "SELECT COUNT(1) AS c FROM rag_summaries WHERE project_id = :pid"
        params = {"pid": project_id}
        chunks = 0
        summaries = 0
        try:
            r1 = await self._client.execute(sql1, params)  # type: ignore[union-attr]
            rows = self._iter_rows(r1)
            if rows:
                chunks = int(list(rows)[0].get("c", 0))
        except Exception:
            chunks = 0
        try:
            r2 = await self._client.execute(sql2, params)  # type: ignore[union-attr]
            rows = self._iter_rows(r2)
            if rows:
                summaries = int(list(rows)[0].get("c", 0))
        except Exception:
            summaries = 0
        return {"chunks": chunks, "summaries": summaries}

    async def delete_by_chapters(
        self, project_id: str, chapter_numbers: Sequence[int]
    ) -> None:
        """根据章节编号批量删除对应的上下文数据。."""
        if not self._client or not chapter_numbers:
            return

        await self.ensure_schema()

        if self._provider == "qdrant":
            try:
                flt = Filter(
                    must=[
                        FieldCondition(
                            key="project_id", match=MatchValue(value=project_id)
                        ),
                        FieldCondition(
                            key="chapter_number",
                            match=MatchAny(any=list(chapter_numbers)),
                        ),
                    ]
                )
                self._client.delete(
                    collection_name=self._qdrant_chunks, points_selector=flt
                )  # type: ignore[attr-defined]
                self._client.delete(
                    collection_name=self._qdrant_summaries, points_selector=flt
                )  # type: ignore[attr-defined]
                logger.info(
                    "Qdrant 已删除章节向量: project=%s chapters=%s",
                    project_id,
                    list(chapter_numbers),
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("Qdrant 删除章节向量失败: %s", exc)
            return

        placeholders = ",".join(
            ":chapter_" + str(idx) for idx in range(len(chapter_numbers))
        )
        params = {
            "project_id": project_id,
            **{f"chapter_{idx}": number for idx, number in enumerate(chapter_numbers)},
        }
        chunk_sql = f"""
        DELETE FROM rag_chunks
        WHERE project_id = :project_id
          AND chapter_number IN ({placeholders})
        """
        summary_sql = f"""
        DELETE FROM rag_summaries
        WHERE project_id = :project_id
          AND chapter_number IN ({placeholders})
        """
        try:
            await self._client.execute(chunk_sql, params)  # type: ignore[union-attr]
            await self._client.execute(summary_sql, params)  # type: ignore[union-attr]
            logger.info(
                "已删除章节向量: project=%s chapters=%s",
                project_id,
                list(chapter_numbers),
            )
        except Exception as exc:  # pragma: no cover - 删除失败时记录日志
            logger.error(
                "删除章节向量失败: project=%s chapters=%s error=%s",
                project_id,
                chapter_numbers,
                exc,
            )

    @staticmethod
    def _to_f32_blob(embedding: Sequence[float]) -> bytes:
        """将向量浮点列表编码为 libsql 可识别的 float32 二进制。."""
        return array("f", embedding).tobytes()

    @staticmethod
    def _from_f32_blob(blob: Any) -> list[float]:
        """将数据库中的 BLOB 解码为浮点列表。."""
        if not blob:
            return []
        if isinstance(blob, memoryview):
            blob = blob.tobytes()
        data = array("f")
        data.frombytes(bytes(blob))
        return list(data)

    @staticmethod
    def _cosine_distance(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
        """计算余弦距离（1 - similarity），避免除零。."""
        if not vec_a or not vec_b:
            return 1.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 1.0
        similarity = dot / (norm_a * norm_b)
        return 1.0 - similarity

    async def _query_chunks_with_python_similarity(
        self,
        *,
        project_id: str,
        embedding: Sequence[float],
        top_k: int,
    ) -> list[RetrievedChunk]:
        sql = """
        SELECT
            content,
            chapter_number,
            chapter_title,
            COALESCE(metadata, '{}') AS metadata,
            embedding
        FROM rag_chunks
        WHERE project_id = :project_id
        """
        result = await self._client.execute(sql, {"project_id": project_id})  # type: ignore[union-attr]
        scored: list[RetrievedChunk] = []
        for row in self._iter_rows(result):
            stored_embedding = self._from_f32_blob(row.get("embedding"))
            distance = self._cosine_distance(embedding, stored_embedding)
            scored.append(
                RetrievedChunk(
                    content=row.get("content", ""),
                    chapter_number=row.get("chapter_number", 0),
                    chapter_title=row.get("chapter_title"),
                    score=distance,
                    metadata=self._parse_metadata(row.get("metadata")),
                )
            )
        scored.sort(key=lambda item: item.score)
        return scored[:top_k]

    async def _query_summaries_with_python_similarity(
        self,
        *,
        project_id: str,
        embedding: Sequence[float],
        top_k: int,
    ) -> list[RetrievedSummary]:
        sql = """
        SELECT
            chapter_number,
            title,
            summary,
            embedding
        FROM rag_summaries
        WHERE project_id = :project_id
        """
        result = await self._client.execute(sql, {"project_id": project_id})  # type: ignore[union-attr]
        scored: list[RetrievedSummary] = []
        for row in self._iter_rows(result):
            stored_embedding = self._from_f32_blob(row.get("embedding"))
            distance = self._cosine_distance(embedding, stored_embedding)
            scored.append(
                RetrievedSummary(
                    chapter_number=row.get("chapter_number", 0),
                    title=row.get("title", ""),
                    summary=row.get("summary", ""),
                    score=distance,
                )
            )
        scored.sort(key=lambda item: item.score)
        return scored[:top_k]

    @staticmethod
    def _parse_metadata(raw: Any) -> dict[str, Any]:
        """解析存储的 JSON 文本，确保输出为 dict。."""
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    @staticmethod
    def _iter_rows(result: Any) -> Iterable[dict[str, Any]]:
        """统一处理 libsql 返回的行数据，确保以 dict 形式迭代。."""
        rows = getattr(result, "rows", None)
        if rows is None:
            rows = result
        if not rows:
            return []
        normalized: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                normalized.append(row)
            elif hasattr(row, "_asdict"):
                normalized.append(row._asdict())  # type: ignore[attr-defined]
            else:
                try:
                    normalized.append(dict(row))
                except Exception:  # pragma: no cover - 无法转换时跳过
                    continue
        return normalized

    # -------------------- Qdrant 辅助 --------------------
    @staticmethod
    def _stable_int_id(text: str) -> int:
        """将字符串 ID 稳定映射为 64 位整数，便于 Qdrant 作为 point id 使用。."""
        if not text:
            return 0
        import hashlib

        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # 取前 8 字节为无符号 64 位整数
        return int.from_bytes(digest[:8], byteorder="big", signed=False)

    async def _ensure_qdrant_collection(self, name: str, dim: int) -> None:
        if self._provider != "qdrant" or not self._client:
            return
        try:
            self._client.get_collection(name)  # type: ignore[attr-defined]
            return
        except Exception:
            pass
        try:
            self._client.create_collection(  # type: ignore[attr-defined]
                collection_name=name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            logger.info("Qdrant 已创建集合: %s (dim=%d)", name, dim)
        except Exception as exc:  # pragma: no cover
            logger.error("Qdrant 创建集合失败: %s", exc)


__all__ = [
    "VectorStoreService",
    "RetrievedChunk",
    "RetrievedSummary",
]
