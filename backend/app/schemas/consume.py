"""Schema for consume operation."""
from decimal import Decimal
from pydantic import BaseModel, Field


class ConsumeRequest(BaseModel):
    """Schema for consuming inventory items."""

    quantity: Decimal = Field(..., gt=0, description="Quantity to consume")
