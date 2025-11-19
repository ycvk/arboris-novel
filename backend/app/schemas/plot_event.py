"""情节事件（PlotEvent）的 Pydantic Schema 定义。."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ActEnum(str, Enum):
    """幕枚举."""

    ACT1 = "act1"
    ACT2 = "act2"
    ACT3 = "act3"


class EventTypeEnum(str, Enum):
    """事件类型枚举."""

    MILESTONE = "milestone"  # 里程碑事件
    CONFLICT = "conflict"  # 冲突事件
    DEVELOPMENT = "development"  # 发展事件
    TRANSITION = "transition"  # 过渡事件


class PacingEnum(str, Enum):
    """节奏枚举."""

    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"


class TensionLevelEnum(str, Enum):
    """张力等级枚举."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EventStatusEnum(str, Enum):
    """事件状态枚举."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class PlotEventBase(BaseModel):
    """PlotEvent 基础 Schema."""

    event_id: int = Field(..., description="卷内的事件编号（1, 2, 3...）")
    event_title: str = Field(..., max_length=255, description="事件标题")
    act: ActEnum = Field(..., description="所属的幕")
    arc_index: int = Field(
        ..., ge=0, description="关联到 volume_outline.major_arcs 的索引"
    )
    event_type: EventTypeEnum = Field(..., description="事件类型")
    description: str = Field(..., description="事件描述（200-300字）")
    estimated_chapters: str | None = Field(
        None, max_length=50, description='预估章节数（如"1-2章"）'
    )
    key_points: list[str] | None = Field(None, description="必须完成的关键点")
    pacing: PacingEnum = Field(PacingEnum.MEDIUM, description="节奏")
    tension_level: TensionLevelEnum = Field(
        TensionLevelEnum.MEDIUM, description="张力等级"
    )
    sequence: int = Field(..., ge=1, description="事件在卷内的顺序")


class PlotEventCreate(PlotEventBase):
    """创建 PlotEvent 的 Schema."""

    volume_id: int = Field(..., description="关联到具体的卷")


class PlotEventUpdate(BaseModel):
    """更新 PlotEvent 的 Schema."""

    event_title: str | None = Field(None, max_length=255)
    description: str | None = None
    estimated_chapters: str | None = Field(None, max_length=50)
    key_points: list[str] | None = None
    completed_key_points: list[str] | None = None
    pacing: PacingEnum | None = None
    tension_level: TensionLevelEnum | None = None
    sequence: int | None = Field(None, ge=1)
    progress: int | None = Field(None, ge=0, le=100, description="事件完成度（0-100）")
    status: EventStatusEnum | None = None


class PlotEventResponse(PlotEventBase):
    """PlotEvent 响应 Schema."""

    id: int
    project_id: str
    volume_id: int
    completed_key_points: list[str] | None = None
    progress: int = 0
    status: EventStatusEnum = EventStatusEnum.PENDING
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic 模型配置."""

        from_attributes = True


class PlotEventListResponse(BaseModel):
    """PlotEvent 列表响应 Schema."""

    plot_events: list[PlotEventResponse]
    total_events: int
    act_distribution: dict | None = Field(
        None,
        description="幕分布统计，如 {'act1': {'event_count': 8, 'estimated_chapters': '15-25章'}}",
    )
