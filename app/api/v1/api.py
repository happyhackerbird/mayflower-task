# app/api/v1/api.py
from fastapi import APIRouter

from app.api.v1.endpoints import address, geo

api_v1_router = APIRouter()
api_v1_router.include_router(address.router, prefix="/addresses", tags=["addresses"])
api_v1_router.include_router(geo.router, prefix="/geo", tags=["geo"])

# Add other endpoint routers here if needed in the future
# e.g., api_router.include_router(poems.router, prefix="/poems", tags=["poems"])
