"""SQLAlchemy ORM models for Maintainer OS."""

from datetime import datetime
from enum import Enum

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class IssueStatus(str, Enum):
    open = "open"
    triaged = "triaged"
    resolved = "resolved"
    closed = "closed"


class PRStatus(str, Enum):
    open = "open"
    reviewed = "reviewed"
    approved = "approved"
    merged = "merged"
    closed = "closed"


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    owner: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    installation_id: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    issues: Mapped[list["Issue"]] = relationship(back_populates="repository")
    pull_requests: Mapped[list["PullRequest"]] = relationship(back_populates="repository")
    weekly_reports: Mapped[list["WeeklyReport"]] = relationship(back_populates="repository")
    releases: Mapped[list["Release"]] = relationship(back_populates="repository")


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    github_number: Mapped[int] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(500))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[IssueStatus] = mapped_column(String(50), default=IssueStatus.open)
    triage_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    repository: Mapped[Repository] = relationship(back_populates="issues")


class PullRequest(Base):
    __tablename__ = "pull_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    github_number: Mapped[int] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(500))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PRStatus] = mapped_column(String(50), default=PRStatus.open)
    review_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    repository: Mapped[Repository] = relationship(back_populates="pull_requests")


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    week_start: Mapped[datetime] = mapped_column(DateTime, index=True)
    week_end: Mapped[datetime] = mapped_column(DateTime)
    report_json: Mapped[str] = mapped_column(Text)
    report_markdown: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    repository: Mapped["Repository"] = relationship(back_populates="weekly_reports")


class Release(Base):
    __tablename__ = "releases"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    version: Mapped[str] = mapped_column(String(50), index=True)
    previous_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bump_type: Mapped[str] = mapped_column(String(20))
    changelog_json: Mapped[str] = mapped_column(Text)
    changelog_markdown: Mapped[str] = mapped_column(Text)
    release_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    github_release_id: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    repository: Mapped["Repository"] = relationship(back_populates="releases")
