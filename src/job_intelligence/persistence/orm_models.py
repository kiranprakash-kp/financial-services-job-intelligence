"""SQLAlchemy 2.x ORM models.

SQLite by default; the same models target PostgreSQL by changing DATABASE_URL.
Historical facts (snapshots, ingestion runs) are append-only and never
overwritten. Source URLs and raw source ids are always retained.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    career_site_url: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    jobs: Mapped[list[Job]] = relationship(back_populates="company")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(255), index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)
    trigger_type: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), default="running")

    pages_discovered: Mapped[int] = mapped_column(Integer, default=0)
    jobs_discovered: Mapped[int] = mapped_column(Integer, default=0)
    jobs_fetched: Mapped[int] = mapped_column(Integer, default=0)
    jobs_inserted: Mapped[int] = mapped_column(Integer, default=0)
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0)
    jobs_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    jobs_closed: Mapped[int] = mapped_column(Integer, default=0)
    jobs_failed: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("company_id", "source_job_id", name="uq_company_source_job"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    source_job_id: Mapped[str] = mapped_column(String(255), index=True)
    canonical_key: Mapped[str] = mapped_column(String(255), index=True)
    key_source: Mapped[str] = mapped_column(String(32), default="source_id")

    title: Mapped[str] = mapped_column(Text)
    normalized_title: Mapped[str | None] = mapped_column(Text)
    role_family: Mapped[str | None] = mapped_column(String(64), index=True)
    role_subfamily: Mapped[str | None] = mapped_column(String(64))
    classification_confidence: Mapped[float | None] = mapped_column(Float)

    employment_type: Mapped[str | None] = mapped_column(String(64))
    experience_level: Mapped[str | None] = mapped_column(String(64))
    business_unit: Mapped[str | None] = mapped_column(String(255))
    department: Mapped[str | None] = mapped_column(String(255))

    location_text: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(64), index=True)
    country: Mapped[str | None] = mapped_column(String(64))
    workplace_type: Mapped[str] = mapped_column(String(32), default="unknown")

    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    salary_currency: Mapped[str | None] = mapped_column(String(8))
    salary_period: Mapped[str | None] = mapped_column(String(16))

    description_text: Mapped[str | None] = mapped_column(Text)
    qualifications_text: Mapped[str | None] = mapped_column(Text)
    responsibilities_text: Mapped[str | None] = mapped_column(Text)

    posting_url: Mapped[str] = mapped_column(Text)
    source_posted_at: Mapped[datetime | None] = mapped_column(DateTime)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    missed_crawls: Mapped[int] = mapped_column(Integer, default=0)  # closure grace counter

    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    raw_payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    data_source: Mapped[str] = mapped_column(String(16), default="live", index=True)

    company: Mapped[Company] = relationship(back_populates="jobs")
    locations: Mapped[list[JobLocation]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list[JobSnapshot]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    job_skills: Mapped[list[JobSkill]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobLocation(Base):
    __tablename__ = "job_locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    location_text: Mapped[str] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(64))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    job: Mapped[Job] = relationship(back_populates="locations")


class JobSnapshot(Base):
    __tablename__ = "job_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    ingestion_run_id: Mapped[int | None] = mapped_column(ForeignKey("ingestion_runs.id"))
    captured_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    title: Mapped[str | None] = mapped_column(Text)
    location_text: Mapped[str | None] = mapped_column(Text)
    description_text: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    change_type: Mapped[str] = mapped_column(String(16))
    changed_fields_json: Mapped[dict] = mapped_column(JSON, default=dict)

    job: Mapped[Job] = relationship(back_populates="snapshots")


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    aliases_json: Mapped[list] = mapped_column(JSON, default=list)


class JobSkill(Base):
    __tablename__ = "job_skills"
    __table_args__ = (UniqueConstraint("job_id", "skill_id", name="uq_job_skill"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"), index=True)
    source: Mapped[str] = mapped_column(String(32), default="taxonomy")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_text: Mapped[str | None] = mapped_column(Text)

    job: Mapped[Job] = relationship(back_populates="job_skills")
    skill: Mapped[Skill] = relationship()


class RoleTaxonomy(Base):
    __tablename__ = "role_taxonomy"

    id: Mapped[int] = mapped_column(primary_key=True)
    role_family: Mapped[str] = mapped_column(String(64), index=True)
    role_subfamily: Mapped[str | None] = mapped_column(String(64))
    keywords_json: Mapped[list] = mapped_column(JSON, default=list)


class MonthlyCompanyMetrics(Base):
    __tablename__ = "monthly_company_metrics"
    __table_args__ = (UniqueConstraint("company_id", "year_month", name="uq_company_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    year_month: Mapped[str] = mapped_column(String(7), index=True)  # YYYY-MM
    active_jobs: Mapped[int] = mapped_column(Integer, default=0)
    new_jobs: Mapped[int] = mapped_column(Integer, default=0)
    closed_jobs: Mapped[int] = mapped_column(Integer, default=0)
    updated_jobs: Mapped[int] = mapped_column(Integer, default=0)
    technology_jobs: Mapped[int] = mapped_column(Integer, default=0)
    operations_jobs: Mapped[int] = mapped_column(Integer, default=0)
    risk_jobs: Mapped[int] = mapped_column(Integer, default=0)
    data_ai_jobs: Mapped[int] = mapped_column(Integer, default=0)
    top_skills_json: Mapped[list] = mapped_column(JSON, default=list)
    top_locations_json: Mapped[list] = mapped_column(JSON, default=list)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    data_source: Mapped[str] = mapped_column(String(16), default="live", index=True)
