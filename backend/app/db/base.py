from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    """SQLAlchemy 基类，自动根据类名生成表名。."""

    @declared_attr.directive
    def __tablename__(self) -> str:  # type: ignore[override]
        """自动生成表名，规则：小写类名。"""
        return self.__name__.lower()
