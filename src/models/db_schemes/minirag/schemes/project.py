from .minirag_base import SQLAlchemyBase
from sqlalchemy import Column, Integer, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy import Index
import uuid


class Project(SQLAlchemyBase):

    __tablename__ = "projects"
    
    project_id = Column(Integer, primary_key=True, autoincrement=True)
    project_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)

    # Each project belongs to a specific user (owner).
    # This prevents other users from accessing or modifying the project.
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    owner = relationship("User", back_populates="projects")
    chunks = relationship("DataChunk", back_populates="project")
    assets = relationship("Asset", back_populates="project")

    __table_args__ = (
        Index('ix_project_user_id', user_id),
    )