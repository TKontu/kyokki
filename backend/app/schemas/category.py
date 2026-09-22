from pydantic import BaseModel, Field, computed_field

from app.services.storage import StorageType, storage_type_for_category


class CategoryBase(BaseModel):
    """Base category schema with common fields."""

    id: str = Field(..., description="Category ID (e.g., 'dairy', 'meat', 'produce')")
    display_name: str = Field(..., description="Human-readable category name")
    icon: str | None = Field(None, description="Emoji icon for category")
    default_shelf_life_days: int = Field(
        ..., gt=0, description="Default shelf life in days"
    )
    frozen_shelf_life_days: int | None = Field(
        None,
        gt=0,
        description="How long this keeps frozen, from the day it goes in; null if freezing does not apply (Q12)",
    )
    sort_order: int = Field(0, description="Display sort order")


class CategoryCreate(CategoryBase):
    """Schema for creating a new category."""

    pass


class CategoryUpdate(BaseModel):
    """Schema for updating a category."""

    display_name: str | None = None
    icon: str | None = None
    default_shelf_life_days: int | None = Field(None, gt=0)
    sort_order: int | None = None


class CategoryResponse(CategoryBase):
    """Schema for category API responses."""

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def default_storage(self) -> StorageType:
        """Where products of this category are kept by default (MVP-S3)."""
        return storage_type_for_category(self.id)
