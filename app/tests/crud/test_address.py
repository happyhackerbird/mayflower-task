import pytest
from unittest.mock import patch, AsyncMock, MagicMock, call
from sqlmodel import Session, select

from app import crud
from app.models import AddressCreate, AddressUpdate, Poem, Address

# TODO: Add tests for create_address, get_addresses, update_address, remove_address

# Helper to create mock Poem objects easily
def create_mock_poem(id: int, location_key: str, text: str) -> Poem:
    return Poem(id=id, location_key=location_key, text=text)

@pytest.mark.asyncio
@patch('app.crud.address.geocode_address', new_callable=AsyncMock)
@patch('app.crud.address.crud_poem.find_or_create_poem')
async def test_get_address(mock_find_or_create_poem: MagicMock, mock_geocode_address: AsyncMock, db: Session) -> None:
    """Test getting an address by ID (requires async setup)."""
    # --- Setup: Create an address first (async) ---
    address_in = AddressCreate(
        street="456 Oak Ave", city="Getville", state="GS", zip="67890", country="Getland"
    )
    # Mock dependencies for creation
    mock_standardized_data = {
        "street": "456 Standard Oak Ave", "city": "Getville", "state": "GS", 
        "zip": "67890", "country": "Getland"
    }
    # Define location_key before using it in the f-string
    location_key = "getville|getland"
    mock_poem_obj = create_mock_poem(id=2, location_key=location_key, text=f"Mock poem for {location_key}")
    mock_geocode_address.return_value = mock_standardized_data
    mock_find_or_create_poem.return_value = mock_poem_obj
    
    created_address = await crud.address.create_address(db=db, address_in=address_in)
    assert created_address.id is not None
    # --- Test: Retrieve the created address (synchronous) ---
    # Retrieve the created address
    retrieved_address = crud.address.get_address(db=db, id=created_address.id)

    # Assertions for successful retrieval
    assert retrieved_address is not None
    assert retrieved_address.id == created_address.id
    # Check standardized data persists
    assert retrieved_address.street == mock_standardized_data["street"]
    assert retrieved_address.city == mock_standardized_data["city"]
    assert retrieved_address.location_key == "getville|getland"
    assert retrieved_address.poem_id == mock_poem_obj.id
    
    # Test retrieving non-existent ID
    non_existent_id = created_address.id + 999
    retrieved_non_existent = crud.address.get_address(db=db, id=non_existent_id)
    assert retrieved_non_existent is None

@pytest.mark.asyncio
@patch('app.crud.address.geocode_address', new_callable=AsyncMock)
@patch('app.crud.address.crud_poem.find_or_create_poem')
async def test_get_addresses(mock_find_or_create_poem: MagicMock, mock_geocode_address: AsyncMock, db: Session) -> None:
    """Test retrieving a list of addresses (requires async setup)."""
    # --- Setup: Create multiple addresses (async) ---
    addr1_in = AddressCreate(street="789 Pine Ln", city="Listville", state="LS", zip="11223", country="Listland")
    addr2_in = AddressCreate(street="101 Maple Dr", city="Listville", state="LS", zip="11224", country="Listland")

    # Mock dependencies (same poem for both for simplicity here)
    mock_standardized_data1 = {"street": "789 Std Pine", "city": "Listville", "state": "LS", "zip": "11223", "country": "Listland"}
    mock_standardized_data2 = {"street": "101 Std Maple", "city": "Listville", "state": "LS", "zip": "11224", "country": "Listland"}
    mock_poem_obj = create_mock_poem(id=3, location_key="listville|listland", text="Mock poem for listville|listland")

    # Mock calls for first address
    mock_geocode_address.return_value = mock_standardized_data1
    mock_find_or_create_poem.return_value = mock_poem_obj
    addr1 = await crud.address.create_address(db=db, address_in=addr1_in)

    # Reset mocks and set return values for second address
    mock_geocode_address.reset_mock()
    mock_find_or_create_poem.reset_mock()
    mock_geocode_address.return_value = mock_standardized_data2
    mock_find_or_create_poem.return_value = mock_poem_obj # Same poem
    addr2 = await crud.address.create_address(db=db, address_in=addr2_in)

    # --- Test: Retrieve addresses (synchronous) ---
    # Retrieve all addresses (assuming only these 2 + potentially previous tests exist)
    # A better approach would use a clean DB fixture for isolation
    all_addresses = crud.address.get_addresses(db=db)
    assert len(all_addresses) >= 2 # Check if at least the two created are there

    # Test limit
    limited_addresses = crud.address.get_addresses(db=db, limit=1)
    assert len(limited_addresses) == 1

    # Test skip (assuming >= 2 addresses exist)
    skipped_addresses = crud.address.get_addresses(db=db, skip=1)
    if len(all_addresses) >= 2:
        assert len(skipped_addresses) == len(all_addresses) - 1
        # Check if the skipped one is different from the first of all
        if skipped_addresses: # Ensure list is not empty before indexing
             assert skipped_addresses[0].id != all_addresses[0].id
    else:
         assert len(skipped_addresses) == 0

@pytest.mark.asyncio
@patch('app.crud.address.geocode_address', new_callable=AsyncMock)
@patch('app.crud.address.crud_poem.find_or_create_poem')
async def test_update_address(mock_find_or_create_poem: MagicMock, mock_geocode_address: AsyncMock, db: Session) -> None:
    """Test updating an existing address (requires async setup/call)."""
    # --- Setup: Create an address first (async) ---
    address_in = AddressCreate(
        street="321 Cedar Blvd", city="Updateville", state="US", zip="54321", country="Updateland"
    )
    # Mock dependencies for creation
    mock_standardized_data_orig = {
        "street": "321 Std Cedar Blvd", "city": "Updateville", "state": "US", 
        "zip": "54321", "country": "Updateland"
    }
    mock_poem_orig = create_mock_poem(id=4, location_key="updateville|updateland", text="Original poem for updateville|updateland")
    mock_geocode_address.return_value = mock_standardized_data_orig
    mock_find_or_create_poem.return_value = mock_poem_orig
    created_address = await crud.address.create_address(db=db, address_in=address_in)
    assert created_address.id is not None
    address_id_to_update = created_address.id

    # Reset mocks for the update call
    mock_geocode_address.reset_mock()
    mock_find_or_create_poem.reset_mock()
    
    # --- Test: Update the address (async) ---
    # Define update data
    update_data = AddressUpdate(street="321 Cedar Boulevard", zip="54322")

    # Since city/country not changing, geocode shouldn't be called by update
    # Call update function
    updated_address = await crud.address.update_address(
        db=db, db_obj=created_address, obj_in=update_data
    )

    # Assertions on the returned object (no re-geocode expected)
    mock_geocode_address.assert_not_awaited() # IMPORTANT: Check not called
    mock_find_or_create_poem.assert_not_called() # IMPORTANT: Check not called
    assert updated_address is not None
    assert updated_address.id == created_address.id
    assert updated_address.street == update_data.street # Updated field
    assert updated_address.city == mock_standardized_data_orig["city"] # Original standardized
    assert updated_address.state == mock_standardized_data_orig["state"] # Original standardized
    assert updated_address.zip == update_data.zip # Updated field
    assert updated_address.country == mock_standardized_data_orig["country"] # Original standardized
    assert updated_address.location_key == mock_poem_orig.location_key # Original key
    assert updated_address.poem_id == mock_poem_orig.id # Original poem ID

@pytest.mark.asyncio
@patch('app.crud.address.geocode_address', new_callable=AsyncMock)
@patch('app.crud.address.crud_poem.find_or_create_poem')
async def test_update_address_with_regeocode(mock_find_or_create_poem: MagicMock, mock_geocode_address: AsyncMock, db: Session) -> None:
    """Test updating address where city/country change triggers re-geocode."""
    # --- Setup: Create an address first (async) ---
    address_in = AddressCreate(
        street="1 Old St", city="Old City", state="OS", zip="00001", country="Oldland"
    )
    mock_standardized_data_orig = {"street": "1 Old St", "city": "Old City", "state": "OS", "zip": "00001", "country": "Oldland"}
    mock_poem_orig = create_mock_poem(id=5, location_key="old city|oldland", text="Original poem for old city|oldland")
    mock_geocode_address.return_value = mock_standardized_data_orig
    mock_find_or_create_poem.return_value = mock_poem_orig
    created_address = await crud.address.create_address(db=db, address_in=address_in)
    assert created_address.id is not None

    # Reset mocks for the update call
    mock_geocode_address.reset_mock()
    mock_find_or_create_poem.reset_mock()
    
    # --- Test: Update the address with city/country change (async) ---
    update_data = AddressUpdate(city="New City", country="Newland") # Change city/country

    # Mock dependencies for the re-geocode and new poem lookup
    mock_standardized_data_new = {"street": "1 Old St", "city": "New City", "state": "OS", "zip": "00001", "country": "Newland"}
    mock_poem_new = create_mock_poem(id=6, location_key="new city|newland", text="New poem for new city|newland")
    mock_geocode_address.return_value = mock_standardized_data_new
    mock_find_or_create_poem.return_value = mock_poem_new

    updated_address = await crud.address.update_address(
        db=db, db_obj=created_address, obj_in=update_data
    )

    # Assertions: Check re-geocode happened and new poem linked
    mock_geocode_address.assert_awaited_once() # Check was called
    # Assert call args for geocode (should use new city/country from update_data, others from db_obj)
    mock_geocode_address.assert_awaited_once_with(
        street=created_address.street, # Original street
        city=update_data.city,      # Updated city
        state=created_address.state,    # Original state
        zip_code=created_address.zip,   # Original zip
        country=update_data.country   # Updated country
    )
    mock_find_or_create_poem.assert_called_once_with(db=db, location_key="new city|newland")
    assert updated_address is not None
    assert updated_address.id == created_address.id
    assert updated_address.street == mock_standardized_data_new["street"] # Should use new std data
    assert updated_address.city == mock_standardized_data_new["city"]
    assert updated_address.country == mock_standardized_data_new["country"]
    assert updated_address.location_key == mock_poem_new.location_key # New key
    assert updated_address.poem_id == mock_poem_new.id # New poem ID

@pytest.mark.asyncio
@patch('app.crud.address.geocode_address', new_callable=AsyncMock)
@patch('app.crud.address.crud_poem.find_or_create_poem')
async def test_remove_address(mock_find_or_create_poem: MagicMock, mock_geocode_address: AsyncMock, db: Session) -> None:
    """Test removing an address (requires async setup)."""
    # --- Setup: Create an address first (async) ---
    address_in = AddressCreate(
        street="999 Delete Dr", city="Removeville", state="RS", zip="99999", country="Removeland"
    )
    mock_standardized_data = {"street": "999 Std Delete Dr", "city": "Removeville", "state": "RS", "zip": "99999", "country": "Removeland"}
    mock_poem_obj = create_mock_poem(id=7, location_key="removeville|removeland", text="Mock poem for removeville|removeland")
    mock_geocode_address.return_value = mock_standardized_data
    mock_find_or_create_poem.return_value = mock_poem_obj
    created_address = await crud.address.create_address(db=db, address_in=address_in)
    assert created_address.id is not None
    created_id = created_address.id # Store the ID

    # --- Test: Remove the address (synchronous) ---
    # Call remove function
    removed_address = crud.address.remove_address(db=db, id=created_id)

    # Assertions on the returned object (should match created data)
    assert removed_address is not None
    assert removed_address.id == created_id
    # Check standardized data from creation
    assert removed_address.street == mock_standardized_data["street"]
    assert removed_address.city == mock_standardized_data["city"]
    assert removed_address.location_key == "removeville|removeland"

    # Try to retrieve the removed address
    retrieved_after_remove = crud.address.get_address(db=db, id=created_id)
    assert retrieved_after_remove is None

    # Test removing non-existent ID
    non_existent_id = created_id + 999
    removed_non_existent = crud.address.remove_address(db=db, id=non_existent_id)
    assert removed_non_existent is None

@pytest.mark.asyncio
@patch('app.crud.address.geocode_address', new_callable=AsyncMock)
@patch('app.crud.poem.find_poem_by_location_key')
@patch('app.crud.poem.run_poet_agent')
async def test_create_address_new_poem(
    mock_run_poet_agent: MagicMock,
    mock_find_poem: MagicMock,
    mock_geocode_address: AsyncMock,
    db: Session
) -> None:
    """
    Test creating an address when no poem exists for the location,
    triggering agent invocation and new poem creation.
    """
    # Input data
    address_in = AddressCreate(
        street="1 Poet Ln", city="NewPoemVille", state="NP", zip="98765", country="AgentLand"
    )
    location_key = "newpoemville|agentland"
    mock_poem_text = "A funny rhyme from the agent."
    mock_final_agent_state = {
        "validation_passed": True,
        "validated_poem": mock_poem_text,
        "location": location_key,
        "error_message": None,
        "retry_count": 0,
    }

    # Mock dependencies
    # 1. Geocoder returns standardized data
    mock_standardized_data = {
        "street": "1 Standard Poet Ln", "city": "NewPoemVille", "state": "NP",
        "zip": "98765", "country": "AgentLand"
    }
    mock_geocode_address.return_value = mock_standardized_data
    # 2. DB find returns None (no existing poem)
    mock_find_poem.return_value = None
    # 3. Agent runner returns the mock state dictionary
    mock_run_poet_agent.return_value = mock_final_agent_state

    # Call the async function under test
    db_address = await crud.address.create_address(db=db, address_in=address_in)

    # Assertions
    assert db_address is not None
    assert db_address.id is not None
    # Check standardized data was used
    assert db_address.street == mock_standardized_data["street"]
    assert db_address.city == mock_standardized_data["city"]
    assert db_address.country == mock_standardized_data["country"]
    # Check derived fields
    assert db_address.location_key == location_key
    assert db_address.poem_id is not None # Should have a new poem ID

    # Verify mocks
    mock_geocode_address.assert_awaited_once_with(
        street=address_in.street, city=address_in.city, state=address_in.state,
        zip_code=address_in.zip, country=address_in.country
    )
    mock_find_poem.assert_called_once_with(db=db, location_key=location_key)
    mock_run_poet_agent.assert_called_once_with(location=location_key)

    # Verify the new Poem was actually created in the DB
    # Fetch the associated poem from the DB using the ID
    newly_created_poem = db.get(Poem, db_address.poem_id)
    assert newly_created_poem is not None
    assert newly_created_poem.location_key == location_key
    assert newly_created_poem.text == mock_poem_text

@pytest.mark.asyncio
@patch('app.crud.address.geocode_address', new_callable=AsyncMock)
@patch('app.crud.poem.find_poem_by_location_key')
@patch('app.crud.poem.invoke_agent_and_get_poem')
async def test_create_address_existing_poem(
    mock_invoke_agent: MagicMock,
    mock_find_poem: MagicMock,
    mock_geocode_address: AsyncMock,
    db: Session
) -> None:
    """
    Test creating an address when a poem already exists for the location,
    ensuring the agent is NOT invoked and the existing poem is linked.
    """
    # Input data
    address_in = AddressCreate(
        street="2 Existing Rd", city="OldPoemTown", state="OP", zip="11223", country="ReuseLand"
    )
    location_key = "oldpoemtown|reuseland"

    # --- Setup existing Poem in DB ---
    # (Ideally, use a factory or fixture, but direct creation works for simplicity)
    existing_poem = Poem(location_key=location_key, text="An old classic verse.")
    db.add(existing_poem)
    db.commit()
    db.refresh(existing_poem)
    assert existing_poem.id is not None # Ensure it has an ID
    existing_poem_id = existing_poem.id
    # ---

    # Mock dependencies
    # 1. Geocoder returns standardized data
    mock_standardized_data = {
        "street": "2 Std Existing Rd", "city": "OldPoemTown", "state": "OP",
        "zip": "11223", "country": "ReuseLand"
    }
    mock_geocode_address.return_value = mock_standardized_data
    # 2. DB find returns the existing poem
    mock_find_poem.return_value = existing_poem
    # 3. Agent invoker (should not be called) - mock is already set up

    # Call the async function under test
    db_address = await crud.address.create_address(db=db, address_in=address_in)

    # Assertions
    assert db_address is not None
    assert db_address.id is not None
    # Check standardized data was used
    assert db_address.street == mock_standardized_data["street"]
    assert db_address.city == mock_standardized_data["city"]
    # Check derived fields and poem link
    assert db_address.location_key == location_key
    assert db_address.poem_id == existing_poem_id # Check linked to EXISTING poem

    # Verify mocks
    mock_geocode_address.assert_awaited_once_with(
        street=address_in.street, city=address_in.city, state=address_in.state,
        zip_code=address_in.zip, country=address_in.country
    )
    mock_find_poem.assert_called_once_with(db=db, location_key=location_key)
    mock_invoke_agent.assert_not_called() # CRITICAL: Ensure agent was skipped
