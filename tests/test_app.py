from fastapi import FastAPI

from app.main import app, create_app


def test_create_app_returns_fastapi_application() -> None:
    application = create_app()

    assert isinstance(application, FastAPI)


def test_application_metadata() -> None:
    assert app.title == "WhatsApp Platform API"
    assert app.version == "0.1.0"


def test_openapi_schema_is_available() -> None:
    schema = app.openapi()

    assert schema["info"]["title"] == "WhatsApp Platform API"
    assert schema["info"]["version"] == "0.1.0"
