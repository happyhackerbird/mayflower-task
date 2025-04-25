# app/api/v1/api.py
from fastapi import APIRouter

from app.api.v1.endpoints import address

api_router = APIRouter()
api_router.include_router(address.router, prefix="/addresses", tags=["addresses"])

# Add other endpoint routers here if needed in the future
# e.g., api_router.include_router(poems.router, prefix="/poems", tags=["poems"])
