from fastapi import FastAPI
from .api.router import api_router

app = FastAPI(title="Fridge Logger API")

app.include_router(api_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome to Fridge Logger API"}