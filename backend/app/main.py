from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, places, recommendations, users, ai, ratings

app = FastAPI(title="Reco API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(places.router)
app.include_router(recommendations.router)
app.include_router(users.router)
app.include_router(ai.router)
app.include_router(ratings.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
