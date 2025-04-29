# app/tests/api/v1/test_address_api.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from typing import Optional

from fastapi.testclient import TestClient
from sqlmodel import Session

# Assuming your FastAPI app object is named 'app' in 'main.py'
# Adjust the import if your app object is located elsewhere
from main import app
from app import models
from app.models import Address, Poem # Import DB models for mock return values
import unittest.mock

# Use the client fixture provided by conftest.py
# It should be configured to use the test database

# Helper to create mock DB objects
def create_db_address(id: int, poem_id: Optional[int], **kwargs) -> Address:
    # Simplified Address creation for mocks
    return Address(id=id, poem_id=poem_id, **kwargs)

def create_db_poem(id: int, **kwargs) -> Poem:
    # Simplified Poem creation
    return Poem(id=id, **kwargs)

@patch('app.crud.address.create_address', new_callable=AsyncMock)
@patch('app.crud.poem.get_poem')
def test_create_address_api_success(
    mock_get_poem: MagicMock,
    mock_create_address_crud: AsyncMock,
    client: TestClient, # TestClient fixture from conftest
    # db: Session # Usually not needed directly, client handles requests
):
    """Test successful address creation via POST /api/v1/addresses/"""
    # Input data for the API request body
    address_data = {
        "street": "1 API St", "city": "APItown", "state": "AS", "zip": "12345", "country": "APILand"
    }
    location_key = "apitown|apiland" # Expected key generation

    # Mock the CRUD layer response
    # crud.address.create_address returns a DB Address object
    mock_db_address = create_db_address(
        id=99, poem_id=101, street="1 Std API St", city="APItown", state="AS",
        zip="12345", country="APILand", location_key=location_key
    )
    mock_create_address_crud.return_value = mock_db_address

    # Mock the poem lookup performed by the API endpoint after creation
    mock_poem_text = "A lovely poem from the CRUD layer."
    mock_db_poem = create_db_poem(id=101, text=mock_poem_text, location_key=location_key)
    mock_get_poem.return_value = mock_db_poem

    # Make the API request
    response = client.post("/api/v1/addresses/", json=address_data)

    # Assertions
    assert response.status_code == 201
    response_data = response.json()

    # Check response body structure matches AddressPublic
    assert response_data["id"] == mock_db_address.id
    assert response_data["street"] == mock_db_address.street
    assert response_data["city"] == mock_db_address.city
    assert response_data["state"] == mock_db_address.state
    assert response_data["zip"] == mock_db_address.zip
    assert response_data["country"] == mock_db_address.country
    assert response_data["location_key"] == mock_db_address.location_key
    assert response_data["poem_text"] == mock_poem_text # Check poem text is included

    # Verify mocks were called correctly by the API endpoint
    mock_create_address_crud.assert_awaited_once()
    # Check the AddressCreate model passed to CRUD matches input
    call_args, call_kwargs = mock_create_address_crud.call_args
    crud_input_address = call_kwargs.get('address_in')
    assert crud_input_address is not None
    assert crud_input_address.model_dump() == address_data # Compare dicts

    # Verify get_poem was called by the endpoint to populate the response
    mock_get_poem.assert_called_once_with(db=unittest.mock.ANY, id=mock_db_address.poem_id)

# Test for GET /api/v1/addresses/ (List)
@patch('app.crud.address.get_addresses')
@patch('app.crud.poem.get_poem')
def test_read_addresses_api(
    mock_get_poem: MagicMock,
    mock_get_addresses_crud: MagicMock,
    client: TestClient,
):
    """Test retrieving a list of addresses via GET /api/v1/addresses/"""
    # Mock data
    addr1_db = create_db_address(id=1, poem_id=10, street="1 List St", city="ListCity", state="LS", zip="1", country="LC", location_key="listcity|ls|lc")
    addr2_db = create_db_address(id=2, poem_id=None, street="2 NoPoem Ave", city="ListCity", state="LS", zip="2", country="LC", location_key="listcity|ls|lc") # No poem linked
    poem1_db = create_db_poem(id=10, text="Poem for Addr 1", location_key="listcity|ls|lc")

    mock_get_addresses_crud.return_value = [addr1_db, addr2_db]
    # Mock get_poem to only return poem1 when called with id=10
    mock_get_poem.side_effect = lambda db, id: poem1_db if id == 10 else None

    # Make API request
    response = client.get("/api/v1/addresses/?limit=5") # Use limit param

    # Assertions
    assert response.status_code == 200
    response_data = response.json()
    assert isinstance(response_data, list)
    assert len(response_data) == 2

    # Check first address (with poem)
    assert response_data[0]["id"] == addr1_db.id
    assert response_data[0]["street"] == addr1_db.street
    assert response_data[0]["poem_text"] == poem1_db.text

    # Check second address (without poem)
    assert response_data[1]["id"] == addr2_db.id
    assert response_data[1]["street"] == addr2_db.street
    assert response_data[1]["poem_text"] is None # API should set None if poem_id is None

    # Verify mocks
    mock_get_addresses_crud.assert_called_once_with(db=unittest.mock.ANY, skip=0, limit=5)
    # Check get_poem was called for addr1's poem_id
    mock_get_poem.assert_called_with(db=unittest.mock.ANY, id=addr1_db.poem_id)

# Test for GET /api/v1/addresses/{address_id} (Single)
@patch('app.crud.address.get_address')
@patch('app.crud.poem.get_poem')
def test_read_address_api_success(
    mock_get_poem: MagicMock,
    mock_get_address_crud: MagicMock,
    client: TestClient,
):
    """Test retrieving a single address successfully."""
    address_id = 5
    location_key = "getone|go|gl"
    # Mock data
    addr_db = create_db_address(id=address_id, poem_id=50, street="5 Get St", city="GetOne", state="GO", zip="5", country="GL", location_key=location_key)
    poem_db = create_db_poem(id=50, text="Poem for GetOne", location_key=location_key)

    mock_get_address_crud.return_value = addr_db
    mock_get_poem.return_value = poem_db

    # Make API request
    response = client.get(f"/api/v1/addresses/{address_id}")

    # Assertions
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["id"] == addr_db.id
    assert response_data["street"] == addr_db.street
    assert response_data["poem_text"] == poem_db.text

    # Verify mocks
    mock_get_address_crud.assert_called_once_with(db=unittest.mock.ANY, id=address_id)
    mock_get_poem.assert_called_once_with(db=unittest.mock.ANY, id=addr_db.poem_id)

@patch('app.crud.address.get_address')
def test_read_address_api_not_found(
    mock_get_address_crud: MagicMock,
    client: TestClient,
):
    """Test retrieving a non-existent address."""
    address_id = 999
    mock_get_address_crud.return_value = None # Simulate not found

    # Make API request
    response = client.get(f"/api/v1/addresses/{address_id}")

    # Assertions
    assert response.status_code == 404
    assert response.json()["detail"] == "Address not found"
    mock_get_address_crud.assert_called_once_with(db=unittest.mock.ANY, id=address_id)

# Test for PUT /api/v1/addresses/{address_id}
@pytest.mark.asyncio
@patch('app.crud.address.get_address') # To find the object first
@patch('app.crud.address.update_address', new_callable=AsyncMock) # The actual update CRUD
@patch('app.crud.poem.get_poem') # To populate the response
async def test_update_address_api_success(
    mock_get_poem: MagicMock,
    mock_update_address_crud: AsyncMock,
    mock_get_address_crud: MagicMock,
    client: TestClient,
):
    """Test successfully updating an address."""
    address_id = 8
    update_payload = {"street": "8 Updated Ave", "zip": "888"}
    location_key = "update|up|ul"

    # Mock finding the existing address
    existing_addr_db = create_db_address(id=address_id, poem_id=80, street="8 Old Ave", city="Update", state="UP", zip="8", country="UL", location_key=location_key)
    mock_get_address_crud.return_value = existing_addr_db

    # Mock the result of the update CRUD call
    # Assume no location change, so poem_id remains 80
    updated_addr_db = create_db_address(id=address_id, poem_id=80, street="8 Updated Ave", city="Update", state="UP", zip="888", country="UL", location_key=location_key)
    mock_update_address_crud.return_value = updated_addr_db

    # Mock the poem lookup for the response
    poem_db = create_db_poem(id=80, text="Poem for Update", location_key=location_key)
    mock_get_poem.return_value = poem_db

    # Make API request
    response = client.put(f"/api/v1/addresses/{address_id}", json=update_payload)

    # Assertions
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["id"] == updated_addr_db.id
    assert response_data["street"] == updated_addr_db.street # Updated
    assert response_data["zip"] == updated_addr_db.zip # Updated
    assert response_data["city"] == updated_addr_db.city # Not updated
    assert response_data["poem_text"] == poem_db.text

    # Verify mocks
    mock_get_address_crud.assert_called_once_with(db=unittest.mock.ANY, id=address_id)
    mock_update_address_crud.assert_awaited_once()
    # Check args passed to update_address crud
    call_args, call_kwargs = mock_update_address_crud.call_args
    assert call_kwargs.get('db_obj') == existing_addr_db
    update_obj = call_kwargs.get('obj_in')
    assert update_obj is not None
    assert update_obj.model_dump(exclude_unset=True) == update_payload

    mock_get_poem.assert_called_once_with(db=unittest.mock.ANY, id=updated_addr_db.poem_id)

@pytest.mark.asyncio
@patch('app.crud.address.get_address') # To find the object first
async def test_update_address_api_not_found(
    mock_get_address_crud: MagicMock,
    client: TestClient,
):
    """Test updating a non-existent address."""
    address_id = 998
    update_payload = {"street": "Does not matter"}
    mock_get_address_crud.return_value = None # Simulate not found

    # Make API request
    response = client.put(f"/api/v1/addresses/{address_id}", json=update_payload)

    # Assertions
    assert response.status_code == 404
    assert response.json()["detail"] == "Address not found"
    mock_get_address_crud.assert_called_once_with(db=unittest.mock.ANY, id=address_id)

# Test for DELETE /api/v1/addresses/{address_id}
@patch('app.crud.address.remove_address')
def test_delete_address_api_success(
    mock_remove_address_crud: MagicMock,
    client: TestClient,
):
    """Test successfully deleting an address."""
    address_id = 4
    location_key = "delete|dl|dl"
    # Mock the object returned by the remove CRUD function
    deleted_addr_db = create_db_address(id=address_id, poem_id=40, street="4 Delete St", city="Delete", state="DL", zip="4", country="DL", location_key=location_key)
    mock_remove_address_crud.return_value = deleted_addr_db

    # Make API request
    response = client.delete(f"/api/v1/addresses/{address_id}")

    # Assertions
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["id"] == deleted_addr_db.id
    assert response_data["street"] == deleted_addr_db.street
    assert response_data["poem_text"] is None # Delete response should have poem_text=None

    # Verify mock
    mock_remove_address_crud.assert_called_once_with(db=unittest.mock.ANY, id=address_id)

@patch('app.crud.address.remove_address')
def test_delete_address_api_not_found(
    mock_remove_address_crud: MagicMock,
    client: TestClient,
):
    """Test deleting a non-existent address."""
    address_id = 997
    mock_remove_address_crud.return_value = None # Simulate not found

    # Make API request
    response = client.delete(f"/api/v1/addresses/{address_id}")

    # Assertions
    assert response.status_code == 404
    assert response.json()["detail"] == "Address not found"
    mock_remove_address_crud.assert_called_once_with(db=unittest.mock.ANY, id=address_id)
