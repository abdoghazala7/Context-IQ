from .minirag_base import SQLAlchemyBase
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid


class User(SQLAlchemyBase):

    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    user_api_key = Column(
        String, unique=True, nullable=False, index=True,
        default=lambda: str(uuid.uuid4())
    )
    user_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    projects = relationship("Project", back_populates="owner")

    def __repr__(self):
        return f"<User(user_id={self.user_id}, user_name={self.user_name})>"
