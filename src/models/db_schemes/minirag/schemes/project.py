from .minirag_base import SQLAlchemyBase
from sqlalchemy import Column, Integer, DateTime, func, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy import Index
import uuid


class Project(SQLAlchemyBase):

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=False)
    project_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)

    # Each project belongs to a specific user (owner).
    # Multiple users can have the same project_id; they are distinguished by user_id.
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    owner = relationship("User", back_populates="projects")
    chunks = relationship("DataChunk", back_populates="project")
    assets = relationship("Asset", back_populates="project")

    __table_args__ = (
        UniqueConstraint('project_id', 'user_id', name='uq_project_user'),
        Index('ix_project_user_id', user_id),
        Index('ix_project_project_id', project_id),
    )