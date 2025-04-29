from typing import List, Optional, Any

from sqlmodel import Session, select

from app.models import Address, AddressCreate, AddressUpdate
from app.services.geoapify_client import StandardizedAddress
from app.services.geoapify_client import geocode_address
from app.crud import poem as crud_poem

async def create_address(db: Session, address_in: AddressCreate) -> Address:
    """Create a new address after geocoding and finding/creating its poem.
    Handles poem generation errors gracefully by creating the address without a linked poem.
    """
    # 1. Geocode the input address (raises HTTPException on failure)
    standardized_address_data: StandardizedAddress = await geocode_address(
        street=address_in.street,
        city=address_in.city,
        state=address_in.state,
        zip_code=address_in.zip,
        country=address_in.country
    )
    assert standardized_address_data is not None

    location_key = standardized_address_data.location_key
    associated_poem_id: Optional[int] = None # Initialize poem_id as None

    # 3. Try to find or create the corresponding poem
    try:
        associated_poem = crud_poem.find_or_create_poem(db=db, location_key=location_key)
        associated_poem_id = associated_poem.id # Assign ID if successful
    except ValueError as e:
        # Log the poem generation failure but don't stop address creation
        print(f"Warning: Poem generation/finding failed for {location_key}: {e}")
        # associated_poem_id remains None
    except Exception as e:
        # Log unexpected errors during poem step but still try to create address
        print(f"Warning: Unexpected error during poem step for {location_key}: {e}")
        # associated_poem_id remains None

    # 4. Create the Address record with standardized data and potentially null poem link
    address_dict_for_creation = {
        "street": standardized_address_data.street,
        "city": standardized_address_data.city,
        "state": standardized_address_data.state,
        "zip": standardized_address_data.zip,
        "country": standardized_address_data.country,
        "location_key": location_key,
        "poem_id": associated_poem_id # Use the ID (or None if poem failed)
    }

    db_address = Address(**address_dict_for_creation)
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

    # Check if location-defining fields have actually changed
    if (('city' in update_data and update_data['city'] != db_obj.city) or 
        ('state' in update_data and update_data['state'] != db_obj.state) or 
        ('country' in update_data and update_data['country'] != db_obj.country)):
        needs_regeocode = True

    new_poem_id = db_obj.poem_id
    new_location_key = db_obj.location_key
    standardized_update_data_dict = update_data # Start with direct updates

    if needs_regeocode:
        # Re-geocode with potentially updated city/country/state
        # Use data from potential_new_data which includes the updates
        standardized_address_result: StandardizedAddress = await geocode_address(
            street=potential_new_data['street'],
            city=potential_new_data['city'],
            state=potential_new_data['state'],
            zip_code=potential_new_data['zip'],
            country=potential_new_data['country']
        )
        assert standardized_address_result is not None

        # Determine new location key and find/create poem
        new_location_key = standardized_address_result.location_key
        associated_poem = crud_poem.find_or_create_poem(db=db, location_key=new_location_key)
        new_poem_id = associated_poem.id
        
        # Use standardized data for the update dict, mapping fields correctly
        standardized_update_data_dict = {
            "street": standardized_address_result.street,
            "city": standardized_address_result.city,
            "state": standardized_address_result.state,
            "zip": standardized_address_result.zip,
            "country": standardized_address_result.country,
            # Don't include location_key/poem_id here, set them separately below
        }
    
    # Update the database object fields using the prepared dict
    for field, value in standardized_update_data_dict.items():
        # Only update if the field exists in the dict (handles partial updates too)
        if value is not None: # Check if value is provided in update
             setattr(db_obj, field, value)
    
    # Update location_key and poem_id if re-geocoding occurred
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
