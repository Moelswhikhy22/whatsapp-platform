from __future__ import annotations

from fastapi import APIRouter
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.api.rate_limits import (
    require_integration_admin_rate_limit,
    require_media_url_rate_limit,
)
from app.api.v1.integration_validation import (
    router as integration_validation_router,
)
from app.api.v1.media import (
    router as media_router,
)
from app.main import create_app


MEDIA_SOURCE_PATH = "/messages/{message_id}/media/{media_id}/url"

MEDIA_APP_PATH = "/api/v1/messages/{message_id}/media/{media_id}/url"

INTEGRATION_VALIDATION_SOURCE_PATH = "/integrations/{integration_id}/validate"

INTEGRATION_VALIDATION_APP_PATH = "/api/v1/integrations/{integration_id}/validate"


def _route_by_path(
    router: APIRouter,
    path: str,
) -> APIRoute:
    matches = [
        route for route in router.routes if isinstance(route, APIRoute) and route.path == path
    ]

    assert len(matches) == 1, f"Expected exactly one APIRoute for {path!r}, found {len(matches)}."

    return matches[0]


def _dependency_calls(
    dependant: Dependant,
) -> set[object]:
    calls: set[object] = set()

    for dependency in dependant.dependencies:
        if dependency.call is not None:
            calls.add(dependency.call)

        calls.update(_dependency_calls(dependency))

    return calls


def test_media_route_is_registered_in_application() -> None:
    application = create_app()

    paths = application.openapi()["paths"]

    assert MEDIA_APP_PATH in paths


def test_media_route_has_rate_limit_dependency() -> None:
    route = _route_by_path(
        media_router,
        MEDIA_SOURCE_PATH,
    )

    calls = _dependency_calls(route.dependant)

    assert require_media_url_rate_limit in calls


def test_integration_validation_route_is_registered_in_application() -> None:
    application = create_app()

    paths = application.openapi()["paths"]

    assert INTEGRATION_VALIDATION_APP_PATH in paths


def test_integration_validation_route_has_rate_limit_dependency() -> None:
    route = _route_by_path(
        integration_validation_router,
        INTEGRATION_VALIDATION_SOURCE_PATH,
    )

    calls = _dependency_calls(route.dependant)

    assert require_integration_admin_rate_limit in calls
