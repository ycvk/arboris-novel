from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class RAGRetrievalLog(Base):
    """RAG 检索日志，用于统计检索性能与质量指标。

    仅存储最小必要信息：时间、项目、延迟、召回规模、重复片段比率与提供方。
    """

    __tablename__ = "rag_retrieval_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    latency_ms: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    summary_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    provider: Mapped[str] = mapped_column(String(16), default="libsql")

