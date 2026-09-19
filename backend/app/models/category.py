from sqlalchemy import ARRAY, Column, Integer, String

from app.db.base_class import Base


class Category(Base):
    """Product category with default shelf life settings.

    Categories are seed data that define product types and their default
    expiration periods (e.g., meat=5 days, cheese=25 days).
    """

    __tablename__ = "category"

    id = Column(
        String, primary_key=True, index=True
    )  # e.g., "dairy", "meat", "produce"
    display_name = Column(String, nullable=False)
    icon = Column(String, nullable=True)  # emoji representation
    default_shelf_life_days = Column(Integer, nullable=False)
    # How long this kind of thing keeps in the freezer, counted from the day it goes in
    # (Q12/DEC-10). NULL means freezing does not change the clock for this category -
    # nothing useful happens to a frozen bottle of squash.
    frozen_shelf_life_days = Column(Integer, nullable=True)
    meal_contexts = Column(
        ARRAY(String), nullable=True
    )  # ["breakfast", "cooking", etc.]
    sort_order = Column(Integer, nullable=False, default=0)
