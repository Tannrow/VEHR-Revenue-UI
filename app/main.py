from app.create_app import create_app, get_cors_origins

app = create_app()

__all__ = ["app", "get_cors_origins"]
