from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base

# 自定义列类型：兼容跨数据库环境
BIGINT_PK_TYPE = BigInteger().with_variant(Integer, "sqlite")
LONG_TEXT_TYPE = Text().with_variant(LONGTEXT, "mysql")


class _MetadataAccessor:
    """Descriptor 用于将 `metadata` 访问重定向到 `metadata_`，且保持 Base.metadata 可用。."""

    def __get__(self, instance, owner):
        if instance is None:
            return Base.metadata
        return instance.metadata_

    def __set__(self, instance, value):
        instance.metadata_ = value


class NovelProject(Base):
    """小说项目主表，仅存放轻量级元数据。."""

    __tablename__ = "novel_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    initial_prompt: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)
    metadata = _MetadataAccessor()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped[User] = relationship("User", back_populates="novel_projects")
    blueprint: Mapped[NovelBlueprint | None] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )
    conversations: Mapped[list[NovelConversation]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="NovelConversation.seq",
    )
    characters: Mapped[list[BlueprintCharacter]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="BlueprintCharacter.position",
    )
    relationships_: Mapped[list[BlueprintRelationship]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="BlueprintRelationship.position",
    )
    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Chapter.chapter_number",
    )
    # 新增：总体框架和分卷大纲
    story_framework: Mapped[StoryFramework | None] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )
    volume_outlines: Mapped[list[VolumeOutline]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="VolumeOutline.volume_number",
    )
    # 新增：情节事件（事件驱动系统）
    plot_events: Mapped[list[PlotEvent]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="PlotEvent.sequence",
    )


class NovelConversation(Base):
    """对话记录表，存储概念阶段的连续对话。."""

    __tablename__ = "novel_conversations"

    id: Mapped[int] = mapped_column(
        BIGINT_PK_TYPE, primary_key=True, autoincrement=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(LONG_TEXT_TYPE, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)
    metadata = _MetadataAccessor()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    project: Mapped[NovelProject] = relationship(back_populates="conversations")


class NovelBlueprint(Base):
    """蓝图主体信息（标题、风格等）。."""

    __tablename__ = "novel_blueprints"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), primary_key=True
    )
    title: Mapped[str | None] = mapped_column(String(255))
    target_audience: Mapped[str | None] = mapped_column(String(255))
    genre: Mapped[str | None] = mapped_column(String(128))
    style: Mapped[str | None] = mapped_column(String(128))
    tone: Mapped[str | None] = mapped_column(String(128))
    one_sentence_summary: Mapped[str | None] = mapped_column(Text)
    full_synopsis: Mapped[str | None] = mapped_column(LONG_TEXT_TYPE)
    world_setting: Mapped[dict | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[NovelProject] = relationship(back_populates="blueprint")


class BlueprintCharacter(Base):
    """蓝图角色信息。."""

    __tablename__ = "blueprint_characters"

    id: Mapped[int] = mapped_column(
        BIGINT_PK_TYPE, primary_key=True, autoincrement=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    identity: Mapped[str | None] = mapped_column(String(255))
    personality: Mapped[str | None] = mapped_column(Text)
    goals: Mapped[str | None] = mapped_column(Text)
    abilities: Mapped[str | None] = mapped_column(Text)
    relationship_to_protagonist: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict | None] = mapped_column(JSON)
    position: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[NovelProject] = relationship(back_populates="characters")


class BlueprintRelationship(Base):
    """角色之间的关系。."""

    __tablename__ = "blueprint_relationships"

    id: Mapped[int] = mapped_column(
        BIGINT_PK_TYPE, primary_key=True, autoincrement=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=False
    )
    character_from: Mapped[str] = mapped_column(String(255), nullable=False)
    character_to: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[NovelProject] = relationship(back_populates="relationships_")


class Chapter(Base):
    """章节正文状态，指向选中的版本。."""

    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(
        BIGINT_PK_TYPE, primary_key=True, autoincrement=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=False
    )
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    real_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="not_generated")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    selected_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="SET NULL"), nullable=True
    )

    # 新增：事件驱动系统字段
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("plot_events.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联到 plot_events（事件驱动模式）",
    )
    event_progress: Mapped[int] = mapped_column(
        Integer, default=0, comment="这一章后，事件的完成度"
    )
    act: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="所属的幕（冗余字段，提高查询效率）"
    )

    # 新增：用户实际写作内容（用于滚动生成）
    actual_content: Mapped[str | None] = mapped_column(
        LONG_TEXT_TYPE, nullable=True, comment="用户实际写作/编辑后的内容"
    )
    is_user_edited: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否被用户编辑过"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[NovelProject] = relationship(back_populates="chapters")
    event: Mapped[PlotEvent | None] = relationship(back_populates="chapters")
    versions: Mapped[list[ChapterVersion]] = relationship(
        "ChapterVersion",
        back_populates="chapter",
        cascade="all, delete-orphan",
        order_by="ChapterVersion.created_at",
        primaryjoin="Chapter.id == ChapterVersion.chapter_id",
        foreign_keys="[ChapterVersion.chapter_id]",
    )
    selected_version: Mapped[ChapterVersion | None] = relationship(
        "ChapterVersion",
        foreign_keys=[selected_version_id],
        primaryjoin="Chapter.selected_version_id == ChapterVersion.id",
        post_update=True,
    )
    evaluations: Mapped[list[ChapterEvaluation]] = relationship(
        back_populates="chapter",
        cascade="all, delete-orphan",
        order_by="ChapterEvaluation.created_at",
    )


class ChapterVersion(Base):
    """章节生成的不同版本文本。."""

    __tablename__ = "chapter_versions"

    id: Mapped[int] = mapped_column(
        BIGINT_PK_TYPE, primary_key=True, autoincrement=True
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )
    version_label: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(LONG_TEXT_TYPE, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)
    metadata = _MetadataAccessor()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    chapter: Mapped[Chapter] = relationship(
        "Chapter",
        back_populates="versions",
        foreign_keys=[chapter_id],
    )
    evaluations: Mapped[list[ChapterEvaluation]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class ChapterEvaluation(Base):
    """章节评估记录。."""

    __tablename__ = "chapter_evaluations"

    id: Mapped[int] = mapped_column(
        BIGINT_PK_TYPE, primary_key=True, autoincrement=True
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="CASCADE")
    )
    decision: Mapped[str | None] = mapped_column(String(32))
    feedback: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    chapter: Mapped[Chapter] = relationship(back_populates="evaluations")
    version: Mapped[ChapterVersion | None] = relationship(back_populates="evaluations")


class StoryFramework(Base):
    """总体框架（第 1 层蓝图）：三幕结构、世界观、核心角色。."""

    __tablename__ = "story_frameworks"

    id: Mapped[int] = mapped_column(
        BIGINT_PK_TYPE, primary_key=True, autoincrement=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # 预估总章节数（可调整）
    estimated_total_chapters: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="预估总章节数（如 500-800 章）"
    )

    # 三幕结构（JSON）
    overall_arc: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="三幕结构，每幕包含：title, description, key_milestones",
    )

    # 元数据
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    project: Mapped[NovelProject] = relationship(back_populates="story_framework")


class VolumeOutline(Base):
    """分卷大纲（第 2 层蓝图）：每卷 50-100 章，包含主要情节线。."""

    __tablename__ = "volume_outlines"

    id: Mapped[int] = mapped_column(
        BIGINT_PK_TYPE, primary_key=True, autoincrement=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=False
    )
    volume_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="第几卷（1, 2, 3...）"
    )

    # 分卷信息
    volume_title: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="卷标题，如'觉醒篇'"
    )
    arc_phase: Mapped[str] = mapped_column(
        Enum("opening", "development", "climax", "conclusion", name="arc_phase_enum"),
        default="opening",
        comment="卷的阶段（opening/development/climax/conclusion）",
    )
    volume_goal: Mapped[str] = mapped_column(
        Text, nullable=False, comment="本卷要达成的核心目标"
    )

    # 章节范围（灵活）
    estimated_chapters: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="预估章节数（如 80）"
    )
    actual_start_chapter: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="实际起始章节号"
    )
    actual_end_chapter: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="实际结束章节号（完成后填入）"
    )

    # 完成标准（JSON 数组）
    completion_criteria: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="分卷完成的标志事件"
    )

    # 主要情节线（JSON 数组）
    major_arcs: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="主要情节线，每个包含：title, description, key_events, estimated_chapters",
    )

    # 其他信息
    new_characters: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="本卷新增角色"
    )
    foreshadowing: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="为后续卷埋下的伏笔"
    )

    # 状态
    status: Mapped[str] = mapped_column(
        Enum("draft", "in_progress", "completed", name="volume_status"),
        default="draft",
        comment="分卷状态",
    )

    # 元数据
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    project: Mapped[NovelProject] = relationship(back_populates="volume_outlines")
    plot_events: Mapped[list[PlotEvent]] = relationship(
        back_populates="volume",
        cascade="all, delete-orphan",
        order_by="PlotEvent.sequence",
    )


class PlotEvent(Base):
    """情节事件（事件驱动系统）：每卷的情节事件列表。."""

    __tablename__ = "plot_events"

    id: Mapped[int] = mapped_column(
        BIGINT_PK_TYPE, primary_key=True, autoincrement=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"), nullable=False
    )
    volume_id: Mapped[int] = mapped_column(
        ForeignKey("volume_outlines.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联到具体的卷",
    )
    event_id: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="卷内的事件编号（1, 2, 3...）"
    )
    event_title: Mapped[str] = mapped_column(String(255), nullable=False)
    act: Mapped[str] = mapped_column(
        Enum("act1", "act2", "act3", name="act_enum"),
        nullable=False,
        comment="所属的幕",
    )
    arc_index: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="关联到 volume_outline.major_arcs 的索引"
    )
    event_type: Mapped[str] = mapped_column(
        Enum(
            "milestone", "conflict", "development", "transition", name="event_type_enum"
        ),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text, nullable=False, comment="事件描述（200-300字）"
    )
    estimated_chapters: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment='预估章节数（如"1-2章"）'
    )
    key_points: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="必须完成的关键点"
    )
    completed_key_points: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="已完成的关键点"
    )
    pacing: Mapped[str] = mapped_column(
        Enum("fast", "medium", "slow", name="pacing_enum"),
        default="medium",
        comment="节奏",
    )
    tension_level: Mapped[str] = mapped_column(
        Enum("high", "medium", "low", name="tension_enum"),
        default="medium",
        comment="张力等级",
    )
    sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="事件在卷内的顺序"
    )
    progress: Mapped[int] = mapped_column(
        Integer, default=0, comment="事件完成度（0-100）"
    )
    status: Mapped[str] = mapped_column(
        Enum("pending", "in_progress", "completed", name="event_status_enum"),
        default="pending",
        comment="事件状态",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    project: Mapped[NovelProject] = relationship(back_populates="plot_events")
    volume: Mapped[VolumeOutline] = relationship(back_populates="plot_events")
    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
