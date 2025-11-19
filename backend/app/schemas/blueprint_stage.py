"""蓝图分阶段生成的Schema定义."""

from typing import Any

from pydantic import BaseModel, Field


class Stage1Data(BaseModel):
    """阶段1：核心概念数据."""

    title: str = Field(..., description="小说标题")
    genre: str = Field(..., description="类型/流派")
    tone: str = Field(..., description="基调/风格")
    target_audience: str | None = Field(None, description="目标读者")
    style: str | None = Field(None, description="文风")
    one_sentence_summary: str = Field(..., description="一句话简介")


class Stage2Data(BaseModel):
    """阶段2：故事框架数据."""

    full_synopsis: str = Field(..., description="完整故事梗概")
    world_setting: dict[str, Any] = Field(..., description="世界观设定")


class Stage3Data(BaseModel):
    """阶段3：角色设定数据."""

    characters: list[dict[str, Any]] = Field(..., description="角色列表")
    relationships: list[dict[str, Any]] = Field(..., description="角色关系列表")


class Stage4Data(BaseModel):
    """阶段4：情节事件规划数据（事件驱动模式）."""

    # 事件驱动模式
    plot_events: list[dict[str, Any]] | None = Field(None, description="情节事件列表")
    total_events: int | None = Field(None, description="事件总数")
    act_distribution: dict[str, Any] | None = Field(None, description="幕分布统计")


class BlueprintDraft(BaseModel):
    """蓝图草稿数据."""

    project_id: str
    current_stage: int = Field(..., ge=1, le=4, description="当前所在阶段")
    stage1: Stage1Data | None = None
    stage2: Stage2Data | None = None
    stage3: Stage3Data | None = None
    stage4: Stage4Data | None = None
    updated_at: str | None = None


class StageGenerationRequest(BaseModel):
    """阶段生成请求."""

    stage: int = Field(..., ge=1, le=4, description="要生成的阶段（1-4）")
    previous_data: dict[str, Any] | None = Field(
        None,
        description="前面阶段用户确认的数据，格式：{'stage1': {...}, 'stage2': {...}, ...}",
    )


class StageGenerationResponse(BaseModel):
    """阶段生成响应."""

    stage: int = Field(..., description="当前阶段")
    data: dict[str, Any] = Field(..., description="生成的数据")
    next_stage: int | None = Field(
        None, description="下一阶段编号，如果是最后一阶段则为None"
    )
    ai_message: str | None = Field(None, description="AI的提示信息")


class SaveDraftRequest(BaseModel):
    """保存草稿请求."""

    current_stage: int = Field(..., ge=1, le=4)
    stage1: Stage1Data | None = None
    stage2: Stage2Data | None = None
    stage3: Stage3Data | None = None
    stage4: Stage4Data | None = None


class DraftResponse(BaseModel):
    """草稿响应."""

    exists: bool = Field(..., description="草稿是否存在")
    draft: BlueprintDraft | None = None


class ChapterProgressEvent(BaseModel):
    """章节生成进度事件（用于SSE）."""

    chapter_number: int
    total_chapters: int
    chapter_data: dict[str, Any]
