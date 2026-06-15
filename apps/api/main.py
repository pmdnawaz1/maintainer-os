import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1 import router as v1_router

log = structlog.get_logger()

app = FastAPI(
    title="Maintainer OS API",
    description="AI Co-Maintainer backend",
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.environment == "development")
