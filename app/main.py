"""Main FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import sys

from app.config import get_settings
from app.api.routes import router
from app.api.formulary_routes import router as formulary_router
from app import __version__

# Configure loguru
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)
logger.add(
    "logs/app.log",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    
    app = FastAPI(
        title=settings.app_name,
        description="""AI-powered Support Agent with Formulary Intelligence.

## Features
- **Support Agent**: AI-powered customer support with ticket management
- **Formulary Intelligence**: PDF ingestion, drug data extraction, access scoring, plan comparison
        """,
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routes
    app.include_router(router, prefix="/api/v1", tags=["Support Agent"])
    app.include_router(formulary_router, prefix="/api/v1", tags=["Formulary Intelligence"])
    
    @app.on_event("startup")
    async def startup_event():
        """Application startup event handler."""
        logger.info(f"Starting {settings.app_name} v{__version__}")
        logger.info(f"Environment: {settings.app_env}")
        logger.info(f"LLM Provider: {settings.llm_provider}")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """Application shutdown event handler."""
        logger.info("Shutting down application")
    
    @app.get("/", tags=["Root"])
    async def root():
        """Root endpoint."""
        return {
            "message": f"Welcome to {settings.app_name}",
            "version": __version__,
            "docs": "/docs",
        }
    
    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
