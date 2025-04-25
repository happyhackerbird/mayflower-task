from fastapi import FastAPI
from app.api.v1.api import api_router as api_v1_router

app = FastAPI(title="Address & Lyric Service")

@app.get("/")
async def read_root():
    return {"message": "Welcome to the Address & Lyric Service!"}

# Include the v1 API router
app.include_router(api_v1_router, prefix="/api/v1")

# --- Optional: Create DB and tables on startup --- 
# This is generally recommended for development/testing only.
