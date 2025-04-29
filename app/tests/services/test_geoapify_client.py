import pytest
import os
from dotenv import load_dotenv
from fastapi import HTTPException

from app.services.geoapify_client import geocode_address, StandardizedAddress

# Load environment variables from .env file for the API key
load_dotenv()

# Check if the API key is available, skip if not
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY")
pytestmark = pytest.mark.skipif(not GEOAPIFY_API_KEY, reason="GEOAPIFY_API_KEY not found in environment variables")

@pytest.mark.live_api # Custom marker for tests hitting live APIs
@pytest.mark.asyncio
async def test_geocode_address_live_success():
    """Test geocode_address with a valid address against the live Geoapify API."""
    # A well-known address unlikely to change drastically
    street = "20 W 34th St"
    city = "New York"
    state = "NY"
    zip_code = "10001"
    country = "USA"

    try:
        result = await geocode_address(street, city, state, zip_code, country)
        assert isinstance(result, StandardizedAddress)
        # Geoapify might return slightly different standardizations, 
        # focus on core components being correct.
        assert result.city.lower() == "new york"
        # Allow for variations like 'United States' or 'United States of America'
        assert "united states" in result.country.lower() 
        # Check if other components likely exist (might be None but shouldn't error)
        assert isinstance(result.street, (str, type(None)))
        assert isinstance(result.state, (str, type(None)))
        assert isinstance(result.zip, (str, type(None)))
        assert isinstance(result.location_key, str)

    except HTTPException as e:
        pytest.fail(f"Live Geoapify call failed with HTTPException: {e.detail}")
    except Exception as e:
        pytest.fail(f"Live Geoapify call failed with unexpected exception: {e}")

@pytest.mark.live_api
@pytest.mark.asyncio
async def test_geocode_address_live_failure_bad_address():
    """Test geocode_address with an intentionally bad address against the live API."""
    street = "123 Nonexistent St"
    city = "Notacity"
    state = "NA"
    zip_code = "00000"
    country = "Nowhere"

    with pytest.raises(HTTPException) as exc_info:
        await geocode_address(street, city, state, zip_code, country)
    
    # Expecting a 404 or similar error from Geoapify for unresolvable address
    assert exc_info.value.status_code == 404
    assert "Could not resolve address" in exc_info.value.detail
