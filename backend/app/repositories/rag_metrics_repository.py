from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.rag_metrics import RAGRetrievalLog


class RAGMetricsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(
        self,
        *,
        project_id: str,
        latency_ms: int,
        chunk_count: int,
        summary_count: int,
        duplicate_ratio: float,
        provider: str,
        occurred_at: datetime | None = None,
    ) -> None:
        record = RAGRetrievalLog(
            project_id=project_id,
            occurred_at=occurred_at,
            latency_ms=latency_ms,
            chunk_count=chunk_count,
            summary_count=summary_count,
            duplicate_ratio=duplicate_ratio,
            provider=provider,
        )
        self.session.add(record)
        await self.session.commit()

    async def window_stats(self, days: int = 7) -> dict:
        since = datetime.utcnow() - timedelta(days=days)

        # 平均延迟
        stmt_avg = select(func.avg(RAGRetrievalLog.latency_ms)).where(
            RAGRetrievalLog.occurred_at >= since
        )
        # 空召回率：chunks+summaries==0 的占比
        stmt_cnt = select(
            func.count(RAGRetrievalLog.id),
            func.sum(
                func.case(
                    (
                        (
                            RAGRetrievalLog.chunk_count + RAGRetrievalLog.summary_count
                            == 0,
                            1,
                        ),
                    ),
                    else_=0,
                )
            ),
        ).where(RAGRetrievalLog.occurred_at >= since)
        # 重复片段率：duplicate_ratio 的平均
        stmt_dup = select(func.avg(RAGRetrievalLog.duplicate_ratio)).where(
            RAGRetrievalLog.occurred_at >= since
        )

        total_count = 0
        empty_count = 0
        avg_latency = None
        avg_dup = None

        avg_res = await self.session.execute(stmt_avg)
        avg_latency = avg_res.scalar()

        cnt_res = await self.session.execute(stmt_cnt)
        row = cnt_res.first()
        if row:
            total_count = int(row[0] or 0)
            empty_count = int(row[1] or 0)

        dup_res = await self.session.execute(stmt_dup)
        avg_dup = dup_res.scalar()

        empty_rate = (empty_count / total_count) if total_count > 0 else None

        return {
            "avg_latency_ms": float(avg_latency) if avg_latency is not None else None,
            "empty_rate": float(empty_rate) if empty_rate is not None else None,
            "duplicate_rate": float(avg_dup) if avg_dup is not None else None,
            "total": total_count,
        }
