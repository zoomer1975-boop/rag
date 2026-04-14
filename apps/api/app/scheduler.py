"""URL 자동 갱신 스케줄러"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()


async def _refresh_due_urls() -> None:
    """next_refresh_at이 현재 시각 이하인 URL 문서를 갱신한다."""
    from app.db.session import AsyncSessionLocal
    from app.models.document import Document
    from app.services.embeddings import get_embedding_client
    from app.services.ingest import IngestService

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document).where(
                Document.source_type == "url",
                Document.next_refresh_at <= now,
                Document.status.notin_(["processing"]),
            )
        )
        docs = result.scalars().all()

    if not docs:
        return

    logger.info("자동 갱신 대상 문서: %d건", len(docs))
    embedding_client = get_embedding_client()

    for doc in docs:
        logger.info("자동 갱신 시작: doc_id=%d title=%s", doc.id, doc.title)
        async with AsyncSessionLocal() as db:
            document = await db.get(Document, doc.id)
            if not document:
                continue
            try:
                # ingest_url 내부 commit 후 document 객체가 expired 되므로 미리 읽어둔다
                interval = document.refresh_interval_hours
                service = IngestService(db=db, embedding_client=embedding_client)
                await service.ingest_url(document, crawl_full_site=False)
                await _update_refresh_timestamps(db, document.id, interval)
                logger.info("자동 갱신 완료: doc_id=%d", doc.id)
            except Exception as exc:
                logger.exception("자동 갱신 실패: doc_id=%d error=%s", doc.id, exc)


async def _update_refresh_timestamps(db, document) -> None:
    from datetime import timedelta
    from sqlalchemy import update
    from app.models.document import Document

    now = datetime.now(timezone.utc)
    interval = document.refresh_interval_hours
    next_refresh = (now + timedelta(hours=interval)) if interval > 0 else None
    await db.execute(
        update(Document)
        .where(Document.id == document.id)
        .values(last_refreshed_at=now, next_refresh_at=next_refresh)
    )
    await db.commit()


def start_scheduler() -> None:
    _scheduler.add_job(
        _refresh_due_urls,
        trigger="interval",
        minutes=15,
        id="url_refresh",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("URL 자동 갱신 스케줄러 시작 (15분 간격)")


def stop_scheduler() -> None:
    _scheduler.shutdown(wait=False)
    logger.info("URL 자동 갱신 스케줄러 종료")
