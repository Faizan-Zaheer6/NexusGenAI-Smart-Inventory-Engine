from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AuditLog


async def log_audit(
    db: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    details: Optional[str] = None,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    await db.flush()
    return entry
