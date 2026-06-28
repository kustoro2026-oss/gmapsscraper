"""SQLAlchemy ORM models — PostgreSQL."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, Numeric, ForeignKey, Enum as SAEnum, Index, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base
import enum


def utcnow():
    return datetime.now(timezone.utc)


# ── Enums ──────────────────────────────────────────────────────────

class PackageType(str, enum.Enum):
    starter = "starter"
    basic = "basic"
    pro = "pro"
    bisnis = "bisnis"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    success = "success"
    failed = "failed"


class UserRole(str, enum.Enum):
    user = "user"
    admin = "admin"


# ── Tables ─────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)
    role = Column(SAEnum(UserRole), default=UserRole.user, nullable=False)
    is_banned = Column(Boolean, default=False, server_default=text('false'), nullable=False)
    banned_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    api_key = relationship("ApiKey", back_populates="user", uselist=False)
    licenses = relationship("License", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")
    usage_logs = relationship("UsageLog", back_populates="user")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    key = Column(String(64), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="api_key")


class License(Base):
    __tablename__ = "licenses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    package = Column(SAEnum(PackageType), nullable=False)
    total_quota = Column(Integer, nullable=False)
    used_quota = Column(Integer, default=0, nullable=False)
    max_scrolls = Column(Integer, default=10, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="licenses")
    transactions = relationship("Transaction", back_populates="license")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    license_id = Column(UUID(as_uuid=True), ForeignKey("licenses.id"), nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)
    duitku_order_id = Column(String(100), unique=True, nullable=False)
    reference = Column(String(100), nullable=True)
    product = Column(SAEnum(PackageType), nullable=False)
    status = Column(SAEnum(TransactionStatus), default=TransactionStatus.pending, nullable=False, index=True)
    payment_method = Column(String(50), nullable=True)
    callback_raw = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="transactions")
    license = relationship("License", back_populates="transactions")


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    license_id = Column(UUID(as_uuid=True), ForeignKey("licenses.id"), nullable=True)
    keyword = Column(String(255), nullable=True)
    results_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="usage_logs")
