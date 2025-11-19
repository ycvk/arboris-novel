from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChoiceOption(BaseModel):
    """前端选择项描述，用于动态 UI 控件。."""

    id: str
    label: str


class UIControl(BaseModel):
    """描述前端应渲染的组件类型与配置。."""

    type: str = Field(..., description="控件类型，如 single_choice/text_input")
    options: list[ChoiceOption] | None = Field(default=None, description="可选项列表")
    placeholder: str | None = Field(default=None, description="输入提示文案")


class ConverseResponse(BaseModel):
    """概念对话接口的统一返回体。."""

    ai_message: str
    ui_control: UIControl
    conversation_state: dict[str, Any]
    is_complete: bool = False
    ready_for_blueprint: bool | None = None


class ConverseRequest(BaseModel):
    """概念对话接口的请求体。."""

    user_input: dict[str, Any]
    conversation_state: dict[str, Any]


class BlueprintProgress(BaseModel):
    """概念对话（新协议）：蓝图进度结构。."""

    core_spark: str | None = None
    genre_tone: str | None = None
    prose_style: str | None = None
    protagonist: str | None = None
    central_conflict: str | None = None
    antagonist: str | None = None
    inciting_incident: str | None = None
    working_titles: list[str] | None = None


class ConverseResponseV2(BaseModel):
    """概念对话新协议的返回体（与 prompts/concept.md 对齐）。."""

    message: str
    question_type: Literal["open_ended", "multiple_choice", "confirmation", "complete"]
    options: list[str] | None = None
    blueprint_progress: BlueprintProgress
    completion_percentage: int
    next_action: Literal["continue", "generate_blueprint"]


class ChapterGenerationStatus(str, Enum):
    NOT_GENERATED = "not_generated"
    GENERATING = "generating"
    EVALUATING = "evaluating"
    SELECTING = "selecting"
    FAILED = "failed"
    EVALUATION_FAILED = "evaluation_failed"
    WAITING_FOR_CONFIRM = "waiting_for_confirm"
    SUCCESSFUL = "successful"


class Chapter(BaseModel):
    chapter_number: int
    title: str
    summary: str
    real_summary: str | None = None
    content: str | None = None
    versions: list[str] | None = None
    evaluation: str | None = None
    generation_status: ChapterGenerationStatus = ChapterGenerationStatus.NOT_GENERATED
    word_count: int = 0
    # 新增：用户实际写作内容
    actual_content: str | None = None
    is_user_edited: bool = False


class Relationship(BaseModel):
    character_from: str
    character_to: str
    description: str


# ============================================================
# 三层蓝图架构 Schema（必须在 Blueprint 之前定义）
# ============================================================


class ActSchema(BaseModel):
    """单个幕的结构."""

    title: str = Field(..., description="幕标题，如'觉醒与成长'")
    description: str = Field(..., description="幕描述，100字左右")
    estimated_chapters: str | None = Field(
        None, description="预估章节数，如'200章'或'150-250章'"
    )
    estimated_volumes: str | None = Field(None, description="预估卷数，如'2-3卷'")
    key_milestones: list[str] = Field(..., description="关键里程碑列表")


class OverallArc(BaseModel):
    """三幕结构.

    核心认知：三幕结构是宏观叙事框架，不等于三卷！
    - 一部 800-1000 章的长篇小说通常有 8-12 卷
    - 第一幕（开端）：约 25%，如 200 章，对应 2-3 卷
    - 第二幕（发展）：约 50%，如 400 章，对应 4-5 卷
    - 第三幕（高潮）：约 25%，如 200 章，对应 2-3 卷
    """

    act1: ActSchema = Field(..., description="第一幕")
    act2: ActSchema = Field(..., description="第二幕")
    act3: ActSchema = Field(..., description="第三幕")


class StoryFrameworkSchema(BaseModel):
    """总体框架 Schema（第 1 层蓝图）."""

    id: int | None = None
    project_id: str | None = None  # 修改为可选，后端会自动填充
    estimated_total_chapters: int | None = Field(
        None, description="预估总章节数（如 500-800 章）"
    )
    estimated_total_volumes: int | None = Field(None, description="预估总卷数（如 10）")
    overall_arc: OverallArc = Field(..., description="三幕结构")
    created_at: str | None = None
    updated_at: str | None = None

    class Config:
        """Pydantic 模型配置."""

        from_attributes = True


class MajorArc(BaseModel):
    """主要情节线."""

    arc_title: str = Field(..., description="情节线标题，如'废柴觉醒'")
    description: str = Field(..., description="情节线描述")
    estimated_chapters: int = Field(
        ..., description="预估章节数（只是预估，不是硬性限制）"
    )
    key_events: list[str] = Field(..., description="关键事件列表")
    actual_start_chapter: int | None = Field(None, description="实际起始章节号")
    actual_end_chapter: int | None = Field(None, description="实际结束章节号")


class VolumeOutlineSchema(BaseModel):
    """分卷大纲 Schema（第 2 层蓝图）.

    重要：一个幕通常包含多个卷
    - 第一卷通常只是第一幕的起始阶段（30-40%）
    - 需要通过 relation_to_act 字段明确本卷在三幕中的定位
    """

    id: int | None = None
    project_id: str | None = None  # 修改为可选，后端会自动填充
    volume_number: int = Field(..., description="第几卷（1, 2, 3...）")
    volume_title: str = Field(..., description="卷标题，如'觉醒篇'")
    arc_phase: Literal["opening", "development", "climax", "conclusion"] = Field(
        "opening", description="卷的阶段（opening/development/climax/conclusion）"
    )
    volume_goal: str = Field(..., description="本卷要达成的核心目标")

    # 章节范围（灵活）
    estimated_chapters: int | None = Field(None, description="预估章节数（如 80）")
    actual_start_chapter: int | None = Field(None, description="实际起始章节号")
    actual_end_chapter: int | None = Field(
        None, description="实际结束章节号（完成后填入）"
    )

    # 完成标准和情节线
    completion_criteria: list[str] | None = Field(
        None, description="分卷完成的标志事件"
    )
    major_arcs: list[MajorArc] | None = Field(None, description="主要情节线")

    # 其他信息
    new_characters: list[str] | None = Field(None, description="本卷新增角色")
    foreshadowing: list[str] | None = Field(None, description="为后续卷埋下的伏笔")

    # 与三幕的关系（新增）
    relation_to_act: str | None = Field(
        None,
        description="本卷在三幕中的定位（100-150字），说明本卷在哪一幕的哪个阶段，要推进哪些三幕目标",
    )

    # 状态
    status: Literal["draft", "in_progress", "completed"] = Field(
        "draft", description="分卷状态"
    )

    created_at: str | None = None
    updated_at: str | None = None

    class Config:
        """Pydantic 模型配置."""

        from_attributes = True


class Stage4Data(BaseModel):
    """阶段4数据：情节事件列表（用于前端兼容性）."""

    plot_events: list[dict[str, Any]] = []


class Blueprint(BaseModel):
    title: str
    target_audience: str = ""
    genre: str = ""
    style: str = ""
    tone: str = ""
    one_sentence_summary: str = ""
    full_synopsis: str = ""
    world_setting: dict[str, Any] = {}
    characters: list[dict[str, Any]] = []
    relationships: list[Relationship] = []

    # 三层蓝图架构（事件驱动模式）
    story_framework: StoryFrameworkSchema | None = None
    volume_outlines: list[VolumeOutlineSchema] = []

    # ⭐ 新增：阶段4数据（情节事件），用于前端兼容性
    stage4_data: Stage4Data | None = None


class NovelProject(BaseModel):
    id: str
    user_id: int
    title: str
    initial_prompt: str
    status: str = "draft"
    metadata: dict[str, Any] | None = None
    conversation_history: list[dict[str, Any]] = []
    blueprint: Blueprint | None = None
    chapters: list[Chapter] = []

    class Config:
        """Pydantic 模型配置."""

        from_attributes = True


class NovelProjectSummary(BaseModel):
    id: str
    title: str
    genre: str
    last_edited: str
    completed_chapters: int
    total_chapters: int


class BlueprintGenerationResponse(BaseModel):
    blueprint: Blueprint
    ai_message: str


class ChapterGenerationResponse(BaseModel):
    ai_message: str
    chapter_versions: list[dict[str, Any]]


class NovelSectionType(str, Enum):
    OVERVIEW = "overview"
    WORLD_SETTING = "world_setting"
    CHARACTERS = "characters"
    RELATIONSHIPS = "relationships"
    CHAPTERS = "chapters"
    VOLUME_MANAGEMENT = "volume_management"
    THREE_LAYER_BLUEPRINT = "three_layer_blueprint"


class NovelSectionResponse(BaseModel):
    section: NovelSectionType
    data: dict[str, Any]


class GenerateChapterRequest(BaseModel):
    chapter_number: int
    writing_notes: str | None = Field(default=None, description="章节额外写作指令")


class SelectVersionRequest(BaseModel):
    chapter_number: int
    version_index: int


class EvaluateChapterRequest(BaseModel):
    chapter_number: int


class DeleteChapterRequest(BaseModel):
    chapter_numbers: list[int]


class BlueprintPatch(BaseModel):
    one_sentence_summary: str | None = None
    full_synopsis: str | None = None
    world_setting: dict[str, Any] | None = None
    characters: list[dict[str, Any]] | None = None
    relationships: list[Relationship] | None = None


class EditChapterRequest(BaseModel):
    chapter_number: int
    content: str


class VolumeCompletionCheckRequest(BaseModel):
    """检查分卷完成度的请求."""

    completed_chapters: list[dict[str, Any]] = Field(
        ..., description="已完成的章节列表，每个包含 chapter_number 和 content"
    )


class VolumeCompletionCheckResponse(BaseModel):
    """检查分卷完成度的响应."""

    is_completed: bool = Field(..., description="分卷是否已完成")
    completed_criteria: list[str] = Field(..., description="已达成的完成标准")
    remaining_criteria: list[str] = Field(..., description="未达成的完成标准")
    estimated_remaining_chapters: int | None = Field(None, description="预估还需多少章")
    suggestion: str = Field(..., description="AI 建议")


class GenerateNextVolumeRequest(BaseModel):
    """生成下一卷大纲的请求."""

    previous_volume_id: int = Field(..., description="上一卷的 ID")
    completed_chapters: list[dict[str, Any]] = Field(
        ..., description="已完成的章节列表，每个包含 chapter_number 和 content"
    )
