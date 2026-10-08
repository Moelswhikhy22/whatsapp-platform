from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _write(relative_path: str, content: str) -> None:
    (ROOT / relative_path).write_text(content, encoding="utf-8")


def _ensure_import(
    content: str,
    import_line: str,
) -> str:
    if import_line in content:
        return content

    marker = "\nfrom app."
    index = content.find(marker)

    if index == -1:
        raise RuntimeError(
            f"Could not find an app import insertion point for: {import_line}"
        )

    return (
        content[: index + 1]
        + import_line
        + "\n"
        + content[index + 1 :]
    )


def _ensure_route_dependency(
    *,
    content: str,
    method: str,
    route_path: str,
    function_name: str,
    dependency_name: str,
) -> str:
    function_marker = f"async def {function_name}("
    function_index = content.find(function_marker)

    if function_index == -1:
        raise RuntimeError(
            f"Could not find endpoint function {function_name!r}."
        )

    route_literal_double = f'"{route_path}"'
    route_literal_single = f"'{route_path}'"

    route_index = content.rfind(
        f"@router.{method}(",
        0,
        function_index,
    )

    if route_index == -1:
        raise RuntimeError(
            f"Could not find @{method} decorator for {function_name!r}."
        )

    decorator_text = content[
        route_index:function_index
    ]

    if (
        route_literal_double not in decorator_text
        and route_literal_single not in decorator_text
    ):
        raise RuntimeError(
            f"Decorator for {function_name!r} does not contain "
            f"expected route {route_path!r}."
        )

    dependency_expression = (
        f"Depends({dependency_name})"
    )

    if dependency_expression in decorator_text:
        return content

    closing = decorator_text.rfind(")\n")

    if closing == -1:
        raise RuntimeError(
            f"Could not locate decorator closing for {function_name!r}."
        )

    insert_at = route_index + closing

    insertion = (
        "    dependencies=[\n"
        f"        Depends({dependency_name}),\n"
        "    ],\n"
    )

    return (
        content[:insert_at]
        + insertion
        + content[insert_at:]
    )


def patch_media() -> None:
    path = "app/api/v1/media.py"
    content = _read(path)

    content = _ensure_import(
        content,
        "from app.api.rate_limits import require_media_url_rate_limit",
    )

    content = _ensure_route_dependency(
        content=content,
        method="get",
        route_path=(
            "/messages/{message_id}/media/"
            "{media_id}/url"
        ),
        function_name="get_media_url",
        dependency_name="require_media_url_rate_limit",
    )

    _write(path, content)


def patch_integration_validation() -> None:
    path = "app/api/v1/integration_validation.py"
    content = _read(path)

    content = _ensure_import(
        content,
        (
            "from app.api.rate_limits import "
            "require_integration_admin_rate_limit"
        ),
    )

    content = _ensure_route_dependency(
        content=content,
        method="post",
        route_path=(
            "/integrations/{integration_id}/validate"
        ),
        function_name="validate_integration",
        dependency_name=(
            "require_integration_admin_rate_limit"
        ),
    )

    _write(path, content)


def patch_router() -> None:
    path = "app/api/v1/router.py"
    content = _read(path)

    content = _ensure_import(
        content,
        (
            "from app.api.v1.media import "
            "router as media_router"
        ),
    )
    content = _ensure_import(
        content,
        (
            "from app.api.v1.integration_validation import "
            "router as integration_validation_router"
        ),
    )

    # Remove the temporary wrapper-router wiring from the previous
    # 24B attempts if it exists. Rate limiting now lives directly
    # on the endpoint decorators, so wrappers are unnecessary.
    wrapper_patterns = (
        r"\nmedia_rate_limited_router\s*=\s*APIRouter\("
        r".*?"
        r"media_rate_limited_router\.include_router\(\s*"
        r"media_router,\s*\)\s*\n",
        r"\nintegration_validation_rate_limited_router\s*=\s*APIRouter\("
        r".*?"
        r"integration_validation_rate_limited_router\.include_router\(\s*"
        r"integration_validation_router,\s*\)\s*\n",
    )

    for pattern in wrapper_patterns:
        content = re.sub(
            pattern,
            "\n",
            content,
            flags=re.DOTALL,
        )

    content = re.sub(
        r"api_router\.include_router\(\s*"
        r"media_rate_limited_router,\s*\)\s*",
        "",
        content,
        flags=re.DOTALL,
    )
    content = re.sub(
        r"api_router\.include_router\(\s*"
        r"integration_validation_rate_limited_router,\s*\)\s*",
        "",
        content,
        flags=re.DOTALL,
    )

    direct_media_pattern = re.compile(
        r"api_router\.include_router\(\s*"
        r"media_router\s*,?\s*\)",
        re.DOTALL,
    )
    direct_validation_pattern = re.compile(
        r"api_router\.include_router\(\s*"
        r"integration_validation_router\s*,?\s*\)",
        re.DOTALL,
    )

    additions: list[str] = []

    if not direct_media_pattern.search(content):
        additions.append(
            "api_router.include_router(\n"
            "    media_router,\n"
            ")\n"
        )

    if not direct_validation_pattern.search(content):
        additions.append(
            "api_router.include_router(\n"
            "    integration_validation_router,\n"
            ")\n"
        )

    if additions:
        content = content.rstrip() + "\n\n" + "\n".join(additions)

    _write(path, content)


def main() -> None:
    patch_media()
    patch_integration_validation()
    patch_router()

    print("24B safe patch applied.")
    print(
        "Modified: app/api/v1/media.py, "
        "app/api/v1/integration_validation.py, "
        "app/api/v1/router.py"
    )


if __name__ == "__main__":
    main()
