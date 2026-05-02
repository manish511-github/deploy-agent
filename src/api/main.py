from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.db import close_pool, run_migrations
from src.task.router import router as agent_router
from src.server.routes.sessions import router as sessions_router
from src.server.routes.permissions import router as permissions_router
from src.install.router import router as install_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_migrations()
    yield
    await close_pool()


app = FastAPI(
    title="DeployAI",
    description="AI-powered Linux server deployment management",
    version="2.0.0",
    lifespan=lifespan,
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
app.include_router(install_router)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
