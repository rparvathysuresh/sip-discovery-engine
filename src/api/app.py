"""
FastAPI application entry point for the SIP Discovery Engine.

Exposes REST endpoints for:
- Data Scope Metadata (/api/v1/metadata)
- Ranked Opportunities (/api/v1/opportunities)
- Evidence Drill-Down (/api/v1/opportunities/{id}/evidence)
- Natural Language Chat (/api/v1/chat)
- AI Evidence Log (/api/v1/evidence-log)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.middleware.refusal_middleware import RefusalMiddleware
from src.api.routes import chat, evidence, evidence_log, metadata, opportunities
from src.utils.logging import get_logger

logger = get_logger("api_app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: perform warm-up or vector indexing on startup."""
    logger.info("SIP Discovery Engine API starting up...")
    try:
        from src.api.routes.chat import get_query_engine
        engine = get_query_engine()
        indexed = engine.index_evidence()
        logger.info("Startup complete: Indexed %d evidence records into vector search", indexed)
    except Exception as e:
        logger.warning("Vector index startup warm-up skipped: %s", e)
    yield
    logger.info("SIP Discovery Engine API shutting down...")


def create_app() -> FastAPI:
    """Create and configure FastAPI instance."""
    app = FastAPI(
        title="SIP Discovery Engine API",
        description="REST backend for SIP investor behavioral discovery, opportunity scoring, and evidence-grounded chat.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # 1. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Refusal Guardrail Middleware (Task 6.9 catch-all)
    app.add_middleware(RefusalMiddleware)

    # 3. Mount Routers
    app.include_router(metadata.router)
    app.include_router(opportunities.router)
    app.include_router(evidence.router)
    app.include_router(chat.router)
    app.include_router(evidence_log.router)

    # 4. Static UI Files (Phase 7 - Task 7.9)
    ui_dir = Path(__file__).resolve().parent.parent / "ui"
    if ui_dir.exists():
        if (ui_dir / "css").exists():
            app.mount("/css", StaticFiles(directory=str(ui_dir / "css")), name="css")
        if (ui_dir / "js").exists():
            app.mount("/js", StaticFiles(directory=str(ui_dir / "js")), name="js")
        app.mount("/ui", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    @app.get("/", tags=["health"])
    def root(request: Request) -> Any:
        accept = request.headers.get("accept", "")
        # If requested by a web browser, serve index.html directly
        if "text/html" in accept and "application/json" not in accept:
            index_path = ui_dir / "index.html"
            if index_path.exists():
                return FileResponse(str(index_path))
        return {
            "name": "SIP Discovery Engine API",
            "version": "1.0.0",
            "status": "online",
            "docs_url": "/docs",
        }

    @app.get("/index.html", include_in_schema=False)
    def index_html() -> Any:
        index_path = ui_dir / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"error": "UI index not found"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.app:app", host="127.0.0.1", port=8000, reload=True)

