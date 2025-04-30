# app/api/v1/endpoints/geo.py
import httpx
from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Any # To represent the JSON response from Geoapify

from app.config import get_settings, Settings

router = APIRouter()

GEOAPIFY_AUTOCOMPLETE_URL = "https://api.geoapify.com/v1/geocode/autocomplete"

@router.get("/autocomplete", response_model=Any)
async def proxy_geoapify_autocomplete(
    query: str = Query(..., min_length=3, description="Address fragment to search for"),
    settings: Settings = Depends(get_settings)
):
    """Proxies autocomplete requests to Geoapify securely."""
    api_key = settings.GEOAPIFY_API_KEY
    if not api_key:
        raise HTTPException(status_code=500, detail="Geoapify API key is not configured on the server.")

    params = {
        "text": query,
        "apiKey": api_key,
        "limit": 5 # Limit suggestions for performance
    }
    headers = {"Accept": "application/json"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(GEOAPIFY_AUTOCOMPLETE_URL, params=params, headers=headers)
            response.raise_for_status() # Raise HTTP errors
            # Return the raw JSON data from Geoapify
            return response.json()
        except httpx.HTTPStatusError as exc:
            # Forward Geoapify's error status code if possible, hide details
            raise HTTPException(
                status_code=exc.response.status_code, 
                detail=f"Error from geocoding service (Status: {exc.response.status_code})"
            )
        except httpx.RequestError as exc:
            print(f"Error contacting Geoapify autocomplete: {exc}") # Log server-side
            raise HTTPException(status_code=503, detail="Could not contact geocoding service.")
        except Exception as exc:
            print(f"Unexpected error in autocomplete proxy: {exc}") # Log server-side
            raise HTTPException(status_code=500, detail="Internal server error during autocomplete.") 