from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, ForeignKey, func
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, ForeignKey, func, JSON
from app.database.schema.session import Base

class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "case4"}

    user_id = Column(String, primary_key=True)
    employee_id = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=False)
    department = Column(String, nullable=False)
    location = Column(String, nullable=False)
    manager = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    status = Column(String, nullable=False)
    identity_verification_level = Column(String, nullable=False)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    created_by = Column(String, default="system", nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    updated_by = Column(String, default="system", nullable=False)
    is_active = Column(Boolean, default="true", nullable=False)

class IAMAccount(Base):
    __tablename__ = "iam_accounts"
    __table_args__ = {"schema": "case4"}

    user_id = Column(String, ForeignKey("case4.users.user_id"), primary_key=True)
    directory_account = Column(String, unique=True, nullable=False)
    account_status = Column(String, nullable=False)
    mfa_enabled = Column(Boolean, nullable=False)
    last_password_change = Column(DateTime, nullable=False)
    failed_login_count = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    created_by = Column(String, default="system", nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    updated_by = Column(String, default="system", nullable=False)
    is_active = Column(Boolean, default="true", nullable=False)

class RunbookRule(Base):
    __tablename__ = "runbook_rules"
    __table_args__ = {"schema": "case4"}

    rule_id = Column(String, primary_key=True)
    workflow = Column(String, nullable=False)
    required_verification = Column(Text, nullable=False)
    confirmation_required = Column(String, nullable=False)
    destructive_action_block = Column(Text, nullable=False)
    sla_target_minutes = Column(Integer, nullable=False)
    policy_version = Column(String, nullable=False)
    owner_team = Column(String, nullable=False)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    created_by = Column(String, default="system", nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    updated_by = Column(String, default="system", nullable=False)
    is_active = Column(Boolean, default="true", nullable=False)

class ActionRequest(Base):
    __tablename__ = "action_requests"
    __table_args__ = {"schema": "case4"}

    request_id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("case4.users.user_id"), nullable=False)
    action_type = Column(String, nullable=False)
    requested_at = Column(DateTime, default=func.now(), nullable=False)
    confirmation_status = Column(String, nullable=False)
    execution_status = Column(String, nullable=False)
    evidence_ref = Column(String, nullable=False)
    outcome_notes = Column(Text, nullable=False)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    created_by = Column(String, default="system", nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    updated_by = Column(String, default="system", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = {"schema": "case4"}

    audit_id = Column(String, primary_key=True)
    request_id = Column(String, ForeignKey("case4.action_requests.request_id"), nullable=False)
    stage = Column(String, nullable=False)
    status = Column(String, nullable=False)
    message = Column(Text, nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    created_by = Column(String, server_default="system", nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    updated_by = Column(String, server_default="system", nullable=False)
    is_active = Column(Boolean, server_default="true", nullable=False)

class ServiceTicket(Base):
    __tablename__ = "service_tickets"
    __table_args__ = {"schema": "case4"}

    ticket_id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("case4.users.user_id", ondelete="CASCADE"), nullable=False)
    status = Column(String, nullable=False)
    priority = Column(String, nullable=False)
    category = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    last_updated = Column(DateTime(timezone=True), nullable=False)
    assigned_group = Column(String, nullable=False)
    summary = Column(Text, nullable=False)

    created_by = Column(String, server_default="system", nullable=False)
    updated_by = Column(String, server_default="system", nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_active = Column(Boolean, server_default="true", nullable=False)

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = {"schema": "case4"}

    chunk_id = Column(String, primary_key=True)
    source_document = Column(String, nullable=False, index=True)
    workflow = Column(String, nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    embedding_model = Column(String, nullable=False)
    embedding_json = Column(JSON, nullable=False)
    chunk_metadata = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(String, server_default="system", nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    updated_by = Column(String, server_default="system", nullable=False)
    is_active = Column(Boolean, server_default="true", nullable=False)    