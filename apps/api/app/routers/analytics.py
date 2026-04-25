"""분석 API — 테넌트별 통계"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import cast, Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import get_tenant
from app.models.chunk import Chunk
from app.models.conversation import Conversation, Message
from app.models.document import Document
from app.models.tenant import Tenant
from app.services.conv_encryption import get_encryptor

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


def _conv_date_filters(start_date: Optional[date], end_date: Optional[date]) -> list:
    filters = []
    if start_date:
        filters.append(
            Conversation.created_at >= datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
        )
    if end_date:
        next_day = end_date + timedelta(days=1)
        filters.append(
            Conversation.created_at < datetime(next_day.year, next_day.month, next_day.day, tzinfo=timezone.utc)
        )
    return filters


@router.get("/stats")
async def get_stats(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """테넌트 통계 — 문서/청크/대화/메시지 수 + 토큰/레이턴시 집계"""
    doc_count = await db.scalar(
        select(func.count(Document.id)).where(Document.tenant_id == tenant.id)
    )
    chunk_count = await db.scalar(
        select(func.count(Chunk.id)).where(Chunk.tenant_id == tenant.id)
    )

    date_filters = _conv_date_filters(start_date, end_date)

    conv_count = await db.scalar(
        select(func.count(Conversation.id)).where(
            Conversation.tenant_id == tenant.id, *date_filters
        )
    )

    assistant_msgs = (
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.tenant_id == tenant.id, Message.role == "assistant", *date_filters)
        .subquery()
    )
    agg = await db.execute(
        select(
            func.count(assistant_msgs.c.id).label("msg_count"),
            func.sum(assistant_msgs.c.input_tokens).label("total_input_tokens"),
            func.sum(assistant_msgs.c.output_tokens).label("total_output_tokens"),
            func.avg(assistant_msgs.c.latency_ms).label("avg_latency_ms"),
        ).select_from(assistant_msgs)
    )
    row = agg.one()

    all_msg_count = await db.scalar(
        select(func.count(Message.id)).join(
            Conversation, Message.conversation_id == Conversation.id
        ).where(Conversation.tenant_id == tenant.id, *date_filters)
    )

    avg_msgs = (
        round((all_msg_count or 0) / (conv_count or 1), 2) if conv_count else 0.0
    )

    return {
        "document_count": doc_count or 0,
        "chunk_count": chunk_count or 0,
        "conversation_count": conv_count or 0,
        "message_count": all_msg_count or 0,
        "total_input_tokens": int(row.total_input_tokens or 0),
        "total_output_tokens": int(row.total_output_tokens or 0),
        "avg_latency_ms": round(float(row.avg_latency_ms), 1) if row.avg_latency_ms else None,
        "avg_messages_per_conversation": avg_msgs,
    }


@router.get("/conversations")
async def list_conversations(
    limit: int = Query(20, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """최근 대화 목록 (message_count 포함)"""
    # 대화별 메시지 수를 서브쿼리로 집계
    msg_count_sq = (
        select(Message.conversation_id, func.count(Message.id).label("message_count"))
        .group_by(Message.conversation_id)
        .subquery()
    )

    result = await db.execute(
        select(Conversation, msg_count_sq.c.message_count)
        .outerjoin(msg_count_sq, Conversation.id == msg_count_sq.c.conversation_id)
        .where(Conversation.tenant_id == tenant.id)
        .order_by(Conversation.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = result.all()
    return [
        {
            "id": c.id,
            "session_id": c.session_id,
            "lang_code": c.lang_code,
            "created_at": c.created_at.isoformat(),
            "message_count": message_count or 0,
        }
        for c, message_count in rows
    ]


@router.get("/conversations/{session_id}/messages")
async def get_conversation_messages(
    session_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """특정 세션의 메시지 조회"""
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.tenant_id == tenant.id,
            Conversation.session_id == session_id,
        )
    )
    conversation = conv_result.scalar_one_or_none()
    if not conversation:
        return []

    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    messages = msg_result.scalars().all()

    enc = get_encryptor()
    dek = await enc.get_dek_readonly(tenant.id, db)

    def _decode(m: Message) -> str:
        if m.content_enc and dek:
            try:
                text = enc.decrypt(m.content_enc, dek)
            except Exception:
                return ""
        else:
            text = m.content or ""
        return text

    return [
        {
            "role": m.role,
            "content": _decode(m),
            "sources": m.sources,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@router.get("/daily-usage")
async def get_daily_usage(
    days: int = Query(30, ge=1, le=365),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """일별 호출 수 + 토큰 사용량 (assistant 메시지 기준)"""
    if start_date or end_date:
        date_filters = _conv_date_filters(start_date, end_date)
    else:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        date_filters = [Conversation.created_at >= cutoff]

    result = await db.execute(
        select(
            cast(Message.created_at, Date).label("date"),
            func.count(Message.id).label("call_count"),
            func.coalesce(func.sum(Message.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(Message.output_tokens), 0).label("output_tokens"),
        )
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant.id,
            Message.role == "assistant",
            *date_filters,
        )
        .group_by(cast(Message.created_at, Date))
        .order_by(cast(Message.created_at, Date))
    )
    return [
        {
            "date": str(row.date),
            "call_count": row.call_count,
            "input_tokens": int(row.input_tokens),
            "output_tokens": int(row.output_tokens),
        }
        for row in result.all()
    ]


@router.get("/language-breakdown")
async def get_language_breakdown(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """언어별 메시지 분포 (lang_code 기준)"""
    date_filters = _conv_date_filters(start_date, end_date)
    result = await db.execute(
        select(
            Conversation.lang_code,
            func.count(Message.id).label("count"),
        )
        .join(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.tenant_id == tenant.id, *date_filters)
        .group_by(Conversation.lang_code)
        .order_by(func.count(Message.id).desc())
    )
    return [
        {"lang_code": row.lang_code, "count": row.count}
        for row in result.all()
    ]
