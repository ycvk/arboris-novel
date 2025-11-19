from datetime import datetime

from pydantic import BaseModel, Field


class Statistics(BaseModel):
    novel_count: int
    user_count: int
    api_request_count: int


class DailyRequestLimit(BaseModel):
    limit: int = Field(..., ge=0, description="匿名用户每日可用次数")


class UpdateLogRead(BaseModel):
    """更新日志读取模型."""

    id: int
    content: str
    created_at: datetime
    created_by: str | None = None
    is_pinned: bool

    class Config:
        """Pydantic 模型配置."""

        from_attributes = True


class UpdateLogBase(BaseModel):
    content: str | None = None
    is_pinned: bool | None = None


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
    title: str | None = None
    chunks: int = 0
    summaries: int = 0


class RAGStatus(BaseModel):
    enabled: bool
    provider: str
    url: str | None = None
    collection_prefix: str | None = None
    embedding_model: str | None = None
    embedding_dim: int | None = None
    top_k_chunks: int
    top_k_summaries: int
    chunk_size: int
    chunk_overlap: int
    total_chunks: int
    total_summaries: int
    top_projects: list[RAGProjectStat] = []
    # 近 7 天运行指标
    avg_latency_ms_7d: float | None = None
    empty_recall_rate_7d: float | None = None
    duplicate_chunk_rate_7d: float | None = None
