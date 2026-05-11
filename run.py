"""Script to run the FastAPI application."""

import uvicorn
from app.config import get_settings


def main():
    """Run the application."""
    settings = get_settings()
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
