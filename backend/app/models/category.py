from sqlalchemy import Column, String, Integer, ARRAY
from app.db.base_class import Base


class Category(Base):
    """Product category with default shelf life settings.

    Categories are seed data that define product types and their default
    expiration periods (e.g., meat=5 days, cheese=25 days).
    """

    __tablename__ = "category"

    id = Column(String, primary_key=True, index=True)  # e.g., "dairy", "meat", "produce"
    display_name = Column(String, nullable=False)
    icon = Column(String, nullable=True)  # emoji representation
    default_shelf_life_days = Column(Integer, nullable=False)
    meal_contexts = Column(ARRAY(String), nullable=True)  # ["breakfast", "cooking", etc.]
    sort_order = Column(Integer, nullable=False, default=0)
