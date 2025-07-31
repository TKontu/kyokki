import uuid
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel

# Shared properties
class ItemBase(BaseModel):
    product_name: Optional[str] = None
    category: Optional[str] = None
    expiry_date: Optional[date] = None
    status: Optional[str] = 'unopened'

# Properties to receive on item creation
class ItemCreate(ItemBase):
    product_name: str
    image_path: str
    category: Optional[str] = None

# Properties to receive on item update
class ItemUpdate(ItemBase):
    pass

# Properties shared by models stored in DB
class ItemInDBBase(ItemBase):
    id: uuid.UUID
    date_added: datetime
    date_modified: datetime
    image_path: str

    class Config:
        from_attributes = True

# Properties to return to client
class Item(ItemInDBBase):
    pass

# Properties stored in DB
class ItemInDB(ItemInDBBase):
    pass
