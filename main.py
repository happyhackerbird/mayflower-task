from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router as api_v1_router

app = FastAPI(title="Address & Lyric Service")

# --- CORS Configuration --- 
origins = [
    "http://localhost:8001",  # Origin for the python -m http.server
    "http://127.0.0.1:8001", # Alternate origin
    "http://localhost",     # Might be needed depending on browser/setup
    "null",               # Sometimes needed for file:// origin (though less relevant now)
    # Add other origins if needed (e.g., your deployed frontend URL)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # Allow specific origins
    allow_credentials=True,
    allow_methods=["*"],        # Allow all methods (GET, POST, PUT, etc.)
    allow_headers=["*"],        # Allow all headers
)
# --- End CORS Configuration ---

@app.get("/")
async def read_root():
    return {"message": "Welcome to the Address & Lyric Service!"}

# Include the v1 API router
app.include_router(api_v1_router, prefix="/api/v1")

# --- Optional: Create DB and tables on startup --- 
# This is generally recommended for development/testing only.
