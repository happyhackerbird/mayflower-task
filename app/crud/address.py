from typing import List, Optional, Any

from sqlmodel import Session, select

from app.models import Address, AddressCreate, AddressUpdate
from app.services.geoapify_client import geocode_address
from app.crud import poem as crud_poem

async def create_address(db: Session, address_in: AddressCreate) -> Address:
    """Create a new address after geocoding and finding/creating its poem."""
    # 1. Geocode the input address
    standardized_address_data = await geocode_address(
        street=address_in.street,
        city=address_in.city,
        state=address_in.state,
        zip_code=address_in.zip,
        country=address_in.country
    )
    # geocode_address raises HTTPException on failure, so we assume success here
    assert standardized_address_data is not None

    # 2. Determine location key
    city = standardized_address_data['city'].lower()
    country = standardized_address_data['country'].lower()
    location_key = f"{city}|{country}"

    # 3. Find or create the corresponding poem
    associated_poem = crud_poem.find_or_create_poem(db=db, location_key=location_key)

    # 4. Create the Address record with standardized data and poem link
    # Use **standardized_address_data to populate fields directly
    db_address = Address(
        **standardized_address_data, # street, city, state, zip, country
        location_key=location_key,
        poem_id=associated_poem.id
    )
    db.add(db_address)
    db.commit()
    db.refresh(db_address)
    return db_address


def get_address(db: Session, id: int) -> Optional[Address]:
    """Get an address by its ID."""
    # TODO: Implement logic
    return db.get(Address, id)


def get_addresses(db: Session, skip: int = 0, limit: int = 100) -> List[Address]:
    """Retrieve a list of addresses."""
    # TODO: Implement logic with skip/limit
    statement = select(Address).offset(skip).limit(limit)
    return db.exec(statement).all()


async def update_address(db: Session, db_obj: Address, obj_in: AddressUpdate) -> Address:
    """Update an address. If city/country changes, re-geocode and update poem link."""
    update_data = obj_in.model_dump(exclude_unset=True)

    needs_regeocode = False
    potential_new_data = db_obj.model_dump() # Start with current data
    potential_new_data.update(update_data) # Apply changes

    if 'city' in update_data or 'country' in update_data:
        needs_regeocode = True

    new_poem_id = db_obj.poem_id
    new_location_key = db_obj.location_key
    standardized_update_data = update_data # Start with direct updates

    if needs_regeocode:
        # Re-geocode with potentially updated city/country
        standardized_address_data = await geocode_address(
            street=potential_new_data['street'],
            city=potential_new_data['city'],
            state=potential_new_data['state'],
            zip_code=potential_new_data['zip'],
            country=potential_new_data['country']
        )
        assert standardized_address_data is not None

        # Determine new location key and find/create poem
        city = standardized_address_data['city'].lower()
        country = standardized_address_data['country'].lower()
        new_location_key = f"{city}|{country}"
        associated_poem = crud_poem.find_or_create_poem(db=db, location_key=new_location_key)
        new_poem_id = associated_poem.id
        # Use standardized data for the update
        standardized_update_data = standardized_address_data
    
    # Update the database object fields
    for field, value in standardized_update_data.items():
        setattr(db_obj, field, value)
    
    # Update location_key and poem_id if they changed
    if needs_regeocode:
        setattr(db_obj, 'location_key', new_location_key)
        setattr(db_obj, 'poem_id', new_poem_id)

    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def remove_address(db: Session, id: int) -> Optional[Address]:
    """Delete an address by its ID."""
    # TODO: Implement logic
    db_obj = db.get(Address, id)
    if not db_obj:
        # Or raise an HTTPException in the API layer
        return None # Or raise error
    db.delete(db_obj)
    db.commit()
    return db_obj # Return the deleted object (or None/True)
