from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from runs.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class GenerationRun(Base):
    __tablename__ = "generation_runs"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_run_idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    input_type: Mapped[str] = mapped_column(String(16), nullable=False)
    input_text: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    source_path: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True, default="queued")
    stage: Mapped[str] = mapped_column(String(100), nullable=False, default="Queued")
    result_json: Mapped[str | None] = mapped_column(Text)
    excel_path: Mapped[str | None] = mapped_column(String(500))
    error_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_token: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
