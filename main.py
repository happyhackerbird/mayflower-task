from fastapi import FastAPI

app = FastAPI(title="Address & Lyric Service")

@app.get("/")
async def read_root():
    return {"message": "Welcome to the Address & Lyric Service!"}
