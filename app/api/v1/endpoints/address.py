# app/api/v1/endpoints/address.py
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app import crud, models
from app.db import get_session

router = APIRouter()


@router.post("/", response_model=models.AddressPublic, status_code=201)
async def create_address_endpoint(
    *,
    db: Session = Depends(get_session),
    address_in: models.AddressCreate,
):
    """
    Create new address. The CRUD layer handles geocoding and 
    finding/generating the associated poem, handling poem errors gracefully.
    """
    try:
        # Call the CRUD function which handles all the logic including poem errors
        db_address = await crud.address.create_address(db=db, address_in=address_in)
        if not db_address:
             raise HTTPException(status_code=500, detail="Address creation failed unexpectedly in CRUD layer.")

        # --- Prepare Response --- 
        poem_text = None # Default to None
        if db_address.poem_id:
            # If poem_id exists, try to fetch the poem text
            db_poem = crud.poem.get_poem(db=db, id=db_address.poem_id)
            if db_poem:
                poem_text = db_poem.text
            else:
                 # Log if linked poem not found (data integrity issue)
                 print(f"Warning: Address {db_address.id} has poem_id {db_address.poem_id}, but Poem not found.")
        else:
            # If poem_id is None, it means poem generation failed (or was skipped)
            # We can optionally set a specific message here instead of just None
            poem_text = "Poem generation failed or skipped." # Optional placeholder message

        # Use model_validate with update to include poem_text
        address_public = models.AddressPublic.model_validate(db_address, update={'poem_text': poem_text})
        return address_public

    # Removed specific ValueError handler, as CRUD now handles it internally.
    # Catch other potential exceptions (e.g., DB connection issues, unexpected errors in CRUD)
    except HTTPException as e:
         # Re-raise HTTPExceptions raised by geocoding
         raise e
    except Exception as e:
        # Catch unexpected errors during the CRUD call or response preparation
        print(f"Unexpected error processing create address request: {e}") 
        raise HTTPException(status_code=500, detail="An unexpected error occurred processing the request.")


@router.get("/{address_id}", response_model=models.AddressPublic)
def read_address_endpoint(
    *, 
    db: Session = Depends(get_session), 
    address_id: int
) -> models.AddressPublic:
    """Retrieve a specific address by ID."""
    db_address = crud.address.get_address(db=db, id=address_id)
    if not db_address:
        raise HTTPException(status_code=404, detail="Address not found")
    # Fetch the associated poem text
    poem_text = None
    if db_address.poem_id:
        db_poem = crud.poem.get_poem(db=db, id=db_address.poem_id)
        if db_poem:
            poem_text = db_poem.text
        else:
             print(f"Warning: Address {db_address.id} has poem_id {db_address.poem_id}, but Poem not found in DB.")

    return models.AddressPublic.model_validate(db_address, update={'poem_text': poem_text})


@router.get("/", response_model=List[models.AddressPublic])
def read_addresses_endpoint(
    *, 
    db: Session = Depends(get_session),
    skip: int = 0,
    limit: int = Query(default=100, le=100), # Use Query for limit validation
) -> List[models.AddressPublic]:
    """Retrieve addresses."""
    db_addresses = crud.address.get_addresses(db=db, skip=skip, limit=limit)
    # Need to enrich each address with its poem text
    addresses_public = []
    for addr in db_addresses:
        poem_text = None
        if addr.poem_id:
            # Use the existing get_poem function from crud.poem
            db_poem = crud.poem.get_poem(db=db, id=addr.poem_id) 
            if db_poem:
                poem_text = db_poem.text
            else:
                 print(f"Warning: Address {addr.id} has poem_id {addr.poem_id}, but Poem not found in DB.")
        addresses_public.append(
            models.AddressPublic.model_validate(addr, update={'poem_text': poem_text})
        )
    return addresses_public


@router.put("/{address_id}", response_model=models.AddressPublic)
async def update_address_endpoint(
    *, 
    db: Session = Depends(get_session), 
    address_id: int, 
    address_in: models.AddressUpdate
) -> models.AddressPublic:
    """Update an address."""
    # First, get the existing DB object
    db_address = crud.address.get_address(db=db, id=address_id)
    if not db_address:
        raise HTTPException(status_code=404, detail="Address not found")
    
    # Call the CRUD update function, passing the db object and input data
    # The CRUD function handles re-geocoding and poem linking if necessary
    try:
        updated_address = await crud.address.update_address(
            db=db, db_obj=db_address, obj_in=address_in
        )
        if not updated_address: # Should not happen if get_address succeeded
            raise HTTPException(status_code=500, detail="Address update failed unexpectedly in CRUD layer.")
            
        # --- Prepare Response ---
        # Fetch the poem text for the potentially updated poem link
        poem_text = None
        if updated_address.poem_id:
            db_poem = crud.poem.get_poem(db=db, id=updated_address.poem_id)
            if db_poem:
                poem_text = db_poem.text
            else:
                 print(f"Warning: Updated Address {updated_address.id} has poem_id {updated_address.poem_id}, but Poem not found.")

        return models.AddressPublic.model_validate(updated_address, update={'poem_text': poem_text})

    except ValueError as e:
        # Catch potential errors from CRUD layer (e.g., geocoding failure)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Unexpected error updating address {address_id}: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred during address update.")


@router.delete("/{address_id}", response_model=models.AddressPublic)
def delete_address_endpoint(
    *, 
    db: Session = Depends(get_session), 
    address_id: int
) -> models.AddressPublic:
    """Delete an address."""
    # Call the CRUD delete function
    # It returns the deleted object or None if not found
    deleted_address = crud.address.remove_address(db=db, id=address_id)
    if not deleted_address:
        raise HTTPException(status_code=404, detail="Address not found")

    # Prepare response (return the data of the deleted object)
    # Set poem_text to None as it's usually not relevant after deletion
    address_public = models.AddressPublic.model_validate(deleted_address, update={'poem_text': None})
    return address_public
