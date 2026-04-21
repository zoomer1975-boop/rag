"""분석 API — 테넌트별 통계"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import get_tenant
from app.models.chunk import Chunk
from app.models.conversation import Conversation, Message
from app.models.document import Document
from app.models.tenant import Tenant

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/stats")
async def get_stats(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """테넌트 통계 — 문서 수, 청크 수, 대화 수, 메시지 수"""
    doc_count = await db.scalar(
        select(func.count(Document.id)).where(Document.tenant_id == tenant.id)
    )
    chunk_count = await db.scalar(
        select(func.count(Chunk.id)).where(Chunk.tenant_id == tenant.id)
    )
    conv_count = await db.scalar(
        select(func.count(Conversation.id)).where(Conversation.tenant_id == tenant.id)
    )
    msg_count = await db.scalar(
        select(func.count(Message.id)).join(
            Conversation, Message.conversation_id == Conversation.id
        ).where(Conversation.tenant_id == tenant.id)
    )

    return {
        "document_count": doc_count or 0,
        "chunk_count": chunk_count or 0,
        "conversation_count": conv_count or 0,
        "message_count": msg_count or 0,
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
    return [
        {
            "role": m.role,
            "content": m.content,
            "sources": m.sources,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]
