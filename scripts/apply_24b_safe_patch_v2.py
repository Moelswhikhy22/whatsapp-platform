from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _path(relative_path: str) -> Path:
    return ROOT / relative_path


def _read(relative_path: str) -> str:
    return _path(relative_path).read_text(encoding="utf-8")


def _write(
    relative_path: str,
    content: str,
) -> None:
    _path(relative_path).write_text(
        content,
        encoding="utf-8",
    )


def _ensure_app_import(
    content: str,
    import_line: str,
) -> str:
    if import_line in content:
        return content

    lines = content.splitlines()

    insertion_index: int | None = None

    for index, line in enumerate(lines):
        if line.startswith("from app.") or line.startswith("import app."):
            insertion_index = index
            break

    if insertion_index is None:
        raise RuntimeError("Could not find the app import section.")

    lines.insert(
        insertion_index,
        import_line,
    )

    return "\n".join(lines) + ("\n" if content.endswith("\n") else "")


def _find_route_decorator_block(
    *,
    content: str,
    function_name: str,
) -> tuple[int, int]:
    function_marker = f"async def {function_name}("
    function_index = content.find(function_marker)

    if function_index == -1:
        raise RuntimeError(f"Endpoint {function_name!r} was not found.")

    decorator_index = content.rfind(
        "@router.",
        0,
        function_index,
    )

    if decorator_index == -1:
        raise RuntimeError(f"Route decorator for {function_name!r} was not found.")

    decorator_text = content[decorator_index:function_index]

    closing_index = decorator_text.rfind(")\n")

    if closing_index == -1:
        raise RuntimeError(f"Could not find closing ')' for {function_name!r} decorator.")

    return (
        decorator_index,
        decorator_index + closing_index,
    )


def _ensure_endpoint_dependency(
    *,
    content: str,
    function_name: str,
    dependency_name: str,
) -> str:
    start, closing = _find_route_decorator_block(
        content=content,
        function_name=function_name,
    )

    decorator_text = content[start:closing]

    dependency_expression = f"Depends({dependency_name})"

    if dependency_expression in decorator_text:
        print(f"{function_name}: dependency already present.")
        return content

    insertion = f"    dependencies=[\n        Depends({dependency_name}),\n    ],\n"

    print(f"{function_name}: adding {dependency_name}.")

    return content[:closing] + insertion + content[closing:]


def patch_media() -> None:
    relative_path = "app/api/v1/media.py"
    content = _read(relative_path)

    content = _ensure_app_import(
        content,
        ("from app.api.rate_limits import require_media_url_rate_limit"),
    )

    content = _ensure_endpoint_dependency(
        content=content,
        function_name="get_media_url",
        dependency_name=("require_media_url_rate_limit"),
    )

    _write(
        relative_path,
        content,
    )


def patch_integration_validation() -> None:
    relative_path = "app/api/v1/integration_validation.py"
    content = _read(relative_path)

    content = _ensure_app_import(
        content,
        ("from app.api.rate_limits import require_integration_admin_rate_limit"),
    )

    content = _ensure_endpoint_dependency(
        content=content,
        function_name="validate_integration",
        dependency_name=("require_integration_admin_rate_limit"),
    )

    _write(
        relative_path,
        content,
    )


def _ensure_router_import(
    content: str,
    *,
    module: str,
    alias: str,
) -> str:
    exact = f"from {module} import router as {alias}"

    if exact in content:
        return content

    multiline_pattern = re.compile(
        rf"from\s+{re.escape(module)}\s+"
        rf"import\s*\(\s*"
        rf"router\s+as\s+{re.escape(alias)}"
        rf"\s*,?\s*\)",
        re.DOTALL,
    )

    if multiline_pattern.search(content):
        return content

    return _ensure_app_import(
        content,
        exact,
    )


def _router_is_included(
    content: str,
    router_name: str,
) -> bool:
    pattern = re.compile(
        rf"\.include_router\(\s*"
        rf"{re.escape(router_name)}"
        rf"\s*,?",
        re.DOTALL,
    )

    return pattern.search(content) is not None


def patch_router() -> None:
    relative_path = "app/api/v1/router.py"
    content = _read(relative_path)

    content = _ensure_router_import(
        content,
        module="app.api.v1.media",
        alias="media_router",
    )

    content = _ensure_router_import(
        content,
        module=("app.api.v1.integration_validation"),
        alias=("integration_validation_router"),
    )

    if not _router_is_included(
        content,
        "media_router",
    ):
        print("router.py: adding media_router.")
        content = (
            content.rstrip()
            + "\n\n"
            + "api_router.include_router(\n"
            + "    media_router,\n"
            + ")\n"
        )
    else:
        print("router.py: media_router already included.")

    if not _router_is_included(
        content,
        "integration_validation_router",
    ):
        print("router.py: adding integration_validation_router.")
        content = (
            content.rstrip()
            + "\n\n"
            + "api_router.include_router(\n"
            + "    integration_validation_router,\n"
            + ")\n"
        )
    else:
        print("router.py: integration_validation_router already included.")

    _write(
        relative_path,
        content,
    )


def verify_files() -> None:
    media = _read("app/api/v1/media.py")
    validation = _read("app/api/v1/integration_validation.py")
    router = _read("app/api/v1/router.py")

    checks = {
        "media dependency": ("Depends(require_media_url_rate_limit)" in media),
        "validation dependency": ("Depends(require_integration_admin_rate_limit)" in validation),
        "media router inclusion": (
            _router_is_included(
                router,
                "media_router",
            )
        ),
        "validation router inclusion": (
            _router_is_included(
                router,
                ("integration_validation_router"),
            )
        ),
    }

    print("")
    print("Static verification:")

    failed: list[str] = []

    for name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name}")

        if not passed:
            failed.append(name)

    if failed:
        raise RuntimeError("24B static verification failed: " + ", ".join(failed))


def main() -> None:
    patch_media()
    patch_integration_validation()
    patch_router()
    verify_files()

    print("")
    print("24B safe patch v2 applied successfully.")


if __name__ == "__main__":
    main()
