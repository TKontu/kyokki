"""Base data structures for receipt parsing.

Pydantic models for LLM extraction with Ollama JSON mode.
"""
from pydantic import BaseModel, Field
from enum import Enum


class StoreChain(str, Enum):
    """Known store chains (expandable)."""
    S_GROUP = "s-group"
    K_GROUP = "k-group"
    LIDL = "lidl"
    UNKNOWN = "unknown"


class ParsedProduct(BaseModel):
    """A single product extracted from a receipt.

    Used by LLM extractor with Ollama JSON mode.
    """
    name: str = Field(..., description="Product name as written on receipt (original language)")
    name_en: str | None = Field(None, description="English translation if not already English")
    quantity: float = Field(default=1.0, description="Number of items", ge=0)
    weight_kg: float | None = Field(None, description="Weight in kilograms if sold by weight", ge=0)
    volume_l: float | None = Field(None, description="Volume in liters if applicable", ge=0)
    unit: str = Field(default="pcs", description="Unit type: pcs, kg, l, or unit")
    price: float | None = Field(None, description="Price in local currency (optional)", ge=0)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage in receipt.ocr_structured."""
        return {
            "name": self.name,
            "name_en": self.name_en,
            "quantity": self.quantity,
            "weight_kg": self.weight_kg,
            "volume_l": self.volume_l,
            "unit": self.unit,
            "price": self.price,
        }


class StoreInfo(BaseModel):
    """Store information extracted from receipt."""
    name: str | None = Field(None, description="Store name from header")
    chain: str | None = Field(None, description="Parent chain if identifiable")
    country: str | None = Field(None, description="Country code (ISO 3166-1 alpha-2)")
    language: str | None = Field(None, description="Primary language of receipt (ISO 639-1)")
    currency: str | None = Field(None, description="Currency code (ISO 4217)")


class ReceiptExtraction(BaseModel):
    """Complete receipt extraction result from LLM.

    This is the top-level schema passed to Ollama's format parameter.
    """
    store: StoreInfo = Field(default_factory=StoreInfo, description="Store information")
    products: list[ParsedProduct] = Field(default_factory=list, description="Extracted products")
    confidence: float | None = Field(None, description="Overall extraction confidence (0-1)", ge=0, le=1)

    # Backward compatibility with simpler schema
    store_name: str | None = Field(None, description="DEPRECATED: Use store.name instead")
    store_chain: str | None = Field(None, description="DEPRECATED: Use store.chain instead")
    country: str | None = Field(None, description="DEPRECATED: Use store.country instead")
    language: str | None = Field(None, description="DEPRECATED: Use store.language instead")
    currency: str | None = Field(None, description="DEPRECATED: Use store.currency instead")

    def get_store_info(self) -> StoreInfo:
        """Get store info, merging deprecated fields if needed."""
        if self.store_name or self.store_chain or self.country or self.language or self.currency:
            # Use deprecated fields if present
            return StoreInfo(
                name=self.store_name or self.store.name,
                chain=self.store_chain or self.store.chain,
                country=self.country or self.store.country,
                language=self.language or self.store.language,
                currency=self.currency or self.store.currency,
            )
        return self.store


class ParseResult(BaseModel):
    """Result from parsing a receipt (template or LLM).

    This is what gets stored in receipt.ocr_structured.
    """
    store_name: str | None = None
    store_chain: str | None = None
    country: str | None = None
    language: str | None = None
    currency: str | None = None
    products: list[dict]  # ParsedProduct.to_dict() results
    parse_method: str = "llm"  # "llm", "template", "hybrid"
    confidence: float = 0.0
    total_items: int = 0
    timestamp: str | None = None
