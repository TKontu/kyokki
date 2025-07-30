import uuid
from sqlalchemy import Column, String, Date, Float, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class Item(Base):
    __tablename__ = "items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_name = Column(String(255), index=True)
    category = Column(String(255), nullable=True)
    expiry_date = Column(Date, nullable=True)
    status = Column(String, default='unopened')
    confidence_score = Column(Float, nullable=True)
    image_path = Column(String(500))
    date_added = Column(DateTime, default=func.now())
    date_modified = Column(DateTime, default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)
    manual_override = Column(Boolean, default=False)
