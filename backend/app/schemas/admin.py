from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Statistics(BaseModel):
    novel_count: int
    user_count: int
    api_request_count: int


class DailyRequestLimit(BaseModel):
    limit: int = Field(..., ge=0, description="匿名用户每日可用次数")


class UpdateLogRead(BaseModel):
    id: int
    content: str
    created_at: datetime
    created_by: Optional[str] = None
    is_pinned: bool

    class Config:
        from_attributes = True


class UpdateLogBase(BaseModel):
    content: Optional[str] = None
    is_pinned: Optional[bool] = None


class UpdateLogCreate(UpdateLogBase):
    content: str


class UpdateLogUpdate(UpdateLogBase):
    pass


class AdminNovelSummary(BaseModel):
    id: str
    title: str
    owner_id: int
    owner_username: str
    genre: str
    last_edited: str
    completed_chapters: int
    total_chapters: int


class RAGProjectStat(BaseModel):
    project_id: str
    title: Optional[str] = None
    chunks: int = 0
    summaries: int = 0


class RAGStatus(BaseModel):
    enabled: bool
    provider: str
    url: Optional[str] = None
    collection_prefix: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_dim: Optional[int] = None
    top_k_chunks: int
    top_k_summaries: int
    chunk_size: int
    chunk_overlap: int
    total_chunks: int
    total_summaries: int
    top_projects: list[RAGProjectStat] = []
    # 近 7 天运行指标
    avg_latency_ms_7d: Optional[float] = None
    empty_recall_rate_7d: Optional[float] = None
    duplicate_chunk_rate_7d: Optional[float] = None
