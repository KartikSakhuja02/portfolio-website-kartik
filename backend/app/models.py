from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func

from .database import Base


class ResumeDocument(Base):
    __tablename__ = "resume_documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, default="Kartik Sakhuja Resume")
    filename = Column(String(255), nullable=False)
    content_type = Column(String(120), nullable=False)
    content_text = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserStatus(Base):
    __tablename__ = "user_status"

    id = Column(Integer, primary_key=True, index=True)
    open_to_work = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
