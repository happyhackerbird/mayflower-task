from typing import Optional
from sqlmodel import Field, SQLModel, Relationship # Added Relationship import

# Shared properties for Address
class AddressBase(SQLModel):
    street: str = Field(index=True)
    city: str = Field(index=True)
    state: str
    zip: str
    country: str = Field(index=True)
    location_key: str = Field(index=True, unique=True, description="Composite key like city|state|country") # Make unique

# Database model, inherits from Base
class Address(AddressBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    poem_id: Optional[int] = Field(default=None, foreign_key="poem.id")
    poem: Optional["Poem"] = Relationship(back_populates="addresses") # Define relationship

# Poem model
class PoemBase(SQLModel):
    text: str
    location_key: str = Field(index=True, unique=True) # Also index and make unique here

class Poem(PoemBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    # Define the one-to-many relationship from Poem to Address
    addresses: list["Address"] = Relationship(back_populates="poem")

# Properties to return to client
class AddressPublic(AddressBase):
    id: int
    poem_text: Optional[str] = None # Include poem text directly

# Properties to receive on creation
class AddressCreate(AddressBase):
    pass

# Properties to receive on update
class AddressUpdate(SQLModel):
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None
