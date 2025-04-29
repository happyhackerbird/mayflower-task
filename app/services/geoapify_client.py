import httpx
from fastapi import HTTPException
from typing import Dict, Optional
from pydantic import BaseModel, Field

from app.config import get_settings

GEOAPIFY_API_URL = "https://api.geoapify.com/v1/geocode/search"

# Define the structure for the standardized address data at the module level
class StandardizedAddress(BaseModel):
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = Field(default=None, alias='postcode') # Geoapify uses 'postcode'
    country: Optional[str] = None
    location_key: str # Composite key for poem linking

async def geocode_address(
    street: str,
    city: str,
    state: str,
    zip_code: str,
    country: str
) -> StandardizedAddress:
    """Geocodes a structured address using Geoapify's free-form text search.

    Args:
        street: Street address.
        city: City name.
        state: State or region.
        zip_code: Postal code.
        country: Country name.

    Returns:
        A StandardizedAddress object with standardized components.
        Raises HTTPException on API errors or if address is not found.
    """
    settings = get_settings()
    api_key = settings.GEOAPIFY_API_KEY

    # Combine components into a free-form text string
    # Geoapify parser is robust, but commas help structure it.
    full_address = f"{street}, {city}, {state} {zip_code}, {country}"

    params = {
        "text": full_address,
        "apiKey": api_key,
        "limit": 1 # We only need the top result
    }
    headers = {"Accept": "application/json"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(GEOAPIFY_API_URL, params=params, headers=headers)
            response.raise_for_status() # Raise exception for 4xx/5xx errors
            data = response.json()

            # Get the features list, default to empty list if key is missing
            features = data.get("features", [])

            # Check if the features list is actually populated
            if features: # This checks if the list is not empty
                # Extract standardized components from the first result's properties
                properties = features[0]['properties']

                # --- Confidence Check --- 
                # Access confidence score safely, default to 0 if keys are missing
                rank_info = properties.get("rank", {})
                confidence = rank_info.get("confidence", 0) # Default to 0 if 'confidence' is missing

                CONFIDENCE_THRESHOLD = 0.7 # Define the minimum acceptable confidence

                if confidence < CONFIDENCE_THRESHOLD:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Could not resolve address: Match confidence ({confidence:.2f}) is below threshold ({CONFIDENCE_THRESHOLD})."
                    )
                # --- End Confidence Check ---

                # Note: Geoapify field names might differ slightly, adjust as needed.
                # Common fields: 'street', 'housenumber', 'city', 'state', 'postcode', 'country'
                
                # Construct the location key components first to check core fields
                city_res = properties.get('city', '').lower()
                state_res = properties.get('state', '').lower()
                country_res = properties.get('country', '').lower()

                # Add a basic check: if essential parts are missing from the *result*, treat as failure
                if not city_res or not country_res:
                    raise HTTPException(
                        status_code=404,
                        detail="Could not resolve address: Geoapify result missing key fields (city/country)."
                    )

                standardized_data = {
                    "street": properties.get('street', street), # Fallback to input if missing
                    "city": properties.get('city', city),
                    "state": properties.get('state', state),
                    "postcode": properties.get('postcode', zip_code),
                    "country": properties.get('country', country),
                    "location_key": f"{city_res}|{state_res}|{country_res}"
                }
                
                # Validate and return using the Pydantic model
                return StandardizedAddress(**standardized_data)
            else: # Handles case where 'features' key is missing OR the list is empty
                raise HTTPException(
                    status_code=404,
                    detail="Could not resolve address: No valid features found in Geoapify response."
                )

        except httpx.HTTPStatusError as exc: # Handle specific HTTP errors from Geoapify
            # You might want to map Geoapify errors (400, 401, etc.) to specific FastAPI HTTPExceptions
            raise HTTPException(
                status_code=exc.response.status_code, 
                detail=f"Geoapify API error: {exc.response.text}"
            )
        except httpx.RequestError as exc: # Handle network/connection errors
            print(f"An error occurred while requesting {exc.request.url!r}.")
            raise HTTPException(status_code=503, detail=f"Error contacting geocoding service: {exc}")
        except Exception as exc: # Catch truly unexpected errors (e.g., parsing issues, logic errors)
            # IMPORTANT: Do NOT catch HTTPException here, let those propagate
            if isinstance(exc, HTTPException):
                raise exc # Re-raise intentionally raised HTTPExceptions

            print(f"Unexpected internal error during geocoding: {exc}") # Replace with proper logging
            raise HTTPException(status_code=500, detail="Internal error during geocoding.")
