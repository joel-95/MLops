import os
from datetime import datetime
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    JSON,
    ForeignKey,
    Float,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./automlops.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Repo(Base):
    __tablename__ = "repos"

    id = Column(String, primary_key=True)  # e.g., "repo_123" or UUID
    sequential_id = Column(Integer, unique=True, nullable=False, index=True)  # For deterministic port (8000 + seq_id)
    repo_name = Column(String, nullable=False)
    github_url = Column(String, nullable=False)
    owner = Column(String, nullable=False)
    mlops_yaml = Column(JSON, nullable=True)  # Snapshot of parsed mlops.yaml
    is_deployed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    runs = relationship("Run", back_populates="repo", cascade="all, delete-orphan")
    deployments = relationship("Deployment", back_populates="repo", cascade="all, delete-orphan")
    retrains = relationship("Retrain", back_populates="repo", cascade="all, delete-orphan")


class Run(Base):
    __tablename__ = "runs"

    id = Column(String, primary_key=True)  # UUID
    repo_id = Column(String, ForeignKey("repos.id"), nullable=False, index=True)
    commit_sha = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending | running | passed | failed
    triggered_by = Column(String, default="push")  # push | automlops-retrain | manual
    metrics_json = Column(JSON, nullable=True)
    quality_gate_result = Column(String, nullable=True)  # passed | failed
    details = Column(JSON, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    repo = relationship("Repo", back_populates="runs")


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(String, primary_key=True)
    repo_id = Column(String, ForeignKey("repos.id"), nullable=False, index=True)
    port = Column(Integer, nullable=False)
    tunnel_url = Column(String, nullable=True)
    deployed_commit_sha = Column(String, nullable=False)
    container_id = Column(String, nullable=True)
    status = Column(String, default="active")  # active | stopped
    deployed_at = Column(DateTime, default=datetime.utcnow)

    repo = relationship("Repo", back_populates="deployments")


class Retrain(Base):
    __tablename__ = "retrains"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(String, ForeignKey("repos.id"), nullable=False, index=True)
    triggered_at = Column(DateTime, default=datetime.utcnow, index=True)
    trigger_reason = Column(String, nullable=False)  # drift | anomaly | manual | drift+anomaly
    status = Column(String, default="triggered")  # triggered | passed | failed | blocked

    repo = relationship("Repo", back_populates="retrains")


class MonitoringState(Base):
    __tablename__ = "monitoring_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(String, ForeignKey("repos.id"), nullable=False, index=True)
    drift_detected = Column(Boolean, default=False)
    drifted_columns = Column(JSON, default=list)
    anomaly_rate = Column(Float, default=0.0)
    anomaly_threshold = Column(Float, default=0.15)
    last_checked_at = Column(DateTime, default=datetime.utcnow)
    version_comparison_html = Column(String, nullable=True)
    production_drift_html = Column(String, nullable=True)
    change_explainer_summary = Column(String, nullable=True)
    change_explainer_details = Column(JSON, nullable=True)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
