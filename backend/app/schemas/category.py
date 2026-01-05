from pydantic import BaseModel, Field


class CategoryBase(BaseModel):
    """Base category schema with common fields."""

    id: str = Field(..., description="Category ID (e.g., 'dairy', 'meat', 'produce')")
    display_name: str = Field(..., description="Human-readable category name")
    icon: str | None = Field(None, description="Emoji icon for category")
    default_shelf_life_days: int = Field(..., gt=0, description="Default shelf life in days")
    meal_contexts: list[str] | None = Field(None, description="Meal contexts where this category is used")
    sort_order: int = Field(0, description="Display sort order")


class CategoryCreate(CategoryBase):
    """Schema for creating a new category."""

    pass


class CategoryUpdate(BaseModel):
    """Schema for updating a category."""

    display_name: str | None = None
    icon: str | None = None
    default_shelf_life_days: int | None = Field(None, gt=0)
    meal_contexts: list[str] | None = None
    sort_order: int | None = None


class CategoryResponse(CategoryBase):
    """Schema for category API responses."""

    model_config = {"from_attributes": True}
