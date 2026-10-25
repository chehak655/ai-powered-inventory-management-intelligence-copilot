from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog


def log_audit_event(
    db: Session,
    action: str,
    resource_type: str,
    company_id: Optional[str] = None,
    user_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """Record an audit log entry in the database."""
    # Sanitize details to never include password or token fields
    clean_details = None
    if details:
        clean_details = {}
        for k, v in details.items():
            if any(secret_term in k.lower() for secret_term in ["password", "token", "secret", "authorization"]):
                clean_details[k] = "[REDACTED]"
            else:
                clean_details[k] = v

    log_entry = AuditLog(
        action=action,
        resource_type=resource_type,
        company_id=company_id,
        user_id=user_id,
        resource_id=resource_id,
        details=clean_details,
        ip_address=ip_address,
    )
    db.add(log_entry)
    # Note: caller commits the transaction or session handles it
    return log_entry
