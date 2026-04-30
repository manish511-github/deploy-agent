from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.task.router import router as agent_router
from src.server.routes.sessions import router as sessions_router
from src.server.routes.permissions import router as permissions_router

app = FastAPI(
    title="DeployAI",
    description="AI-powered Linux server deployment management",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Existing Go agent check-in routes
app.include_router(agent_router)

# New session + streaming routes
app.include_router(sessions_router)
app.include_router(permissions_router)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
