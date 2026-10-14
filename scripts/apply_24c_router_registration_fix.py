from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Important:
# Running:
#     python scripts/something.py
# normally puts /scripts first on sys.path, not the project root.
#
# We must force this repository root to have the highest priority,
# otherwise Python can accidentally import an unrelated third-party
# package named "app" from site-packages.
root_string = str(ROOT)

if root_string in sys.path:
    sys.path.remove(root_string)

sys.path.insert(0, root_string)


# Remove an already-loaded foreign package named "app", if any.
for module_name in list(sys.modules):
    if module_name == "app" or module_name.startswith("app."):
        module = sys.modules.get(module_name)

        module_file = getattr(
            module,
            "__file__",
            None,
        )

        if module_file is None:
            continue

        try:
            module_path = Path(module_file).resolve()

            belongs_to_project = module_path.is_relative_to(ROOT)
        except (
            OSError,
            ValueError,
        ):
            belongs_to_project = False

        if not belongs_to_project:
            sys.modules.pop(
                module_name,
                None,
            )


from fastapi.routing import APIRoute  # noqa: E402


ROUTER_PATH = ROOT / "app" / "api" / "v1" / "router.py"

MEDIA_PATH = "/messages/{message_id}/media/{media_id}/url"

VALIDATION_PATH = "/integrations/{integration_id}/validate"

FALLBACK_MARKER = "# 24C_REQUIRED_ROUTE_REGISTRATION"


def _ensure_import(
    content: str,
    *,
    module: str,
    alias: str,
) -> str:
    direct = f"from {module} import router as {alias}"

    if direct in content:
        return content

    multiline = re.compile(
        rf"from\s+{re.escape(module)}\s+"
        rf"import\s*\(\s*"
        rf"router\s+as\s+{re.escape(alias)}"
        rf"\s*,?\s*\)",
        re.DOTALL,
    )

    if multiline.search(content):
        return content

    lines = content.splitlines()

    insert_at: int | None = None

    for index, line in enumerate(lines):
        if line.startswith("from app.api.v1."):
            insert_at = index
            break

    if insert_at is None:
        raise RuntimeError("Could not find API v1 import section in app/api/v1/router.py.")

    lines.insert(
        insert_at,
        direct,
    )

    return "\n".join(lines) + "\n"


def _has_direct_include(
    content: str,
    router_name: str,
) -> bool:
    pattern = re.compile(
        rf"\bapi_router\.include_router\(\s*"
        rf"{re.escape(router_name)}"
        rf"\s*(?:,|\))",
        re.DOTALL,
    )

    return pattern.search(content) is not None


def _append_include(
    content: str,
    router_name: str,
) -> str:
    return (
        content.rstrip() + "\n\n" + "api_router.include_router(\n" + f"    {router_name},\n" + ")\n"
    )


def _clear_project_api_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "app.api.v1.router" or module_name.startswith("app.api.v1.router."):
            sys.modules.pop(
                module_name,
                None,
            )


def _load_router_module():
    _clear_project_api_modules()

    importlib.invalidate_caches()

    return importlib.import_module("app.api.v1.router")


def _registered_paths() -> set[str]:
    module = _load_router_module()

    return {
        route.path
        for route in module.api_router.routes
        if isinstance(
            route,
            APIRoute,
        )
    }


def _source_router_paths() -> tuple[
    set[str],
    set[str],
]:
    media_module = importlib.import_module("app.api.v1.media")

    validation_module = importlib.import_module("app.api.v1.integration_validation")

    media_paths = {
        route.path
        for route in (media_module.router.routes)
        if isinstance(
            route,
            APIRoute,
        )
    }

    validation_paths = {
        route.path
        for route in (validation_module.router.routes)
        if isinstance(
            route,
            APIRoute,
        )
    }

    return (
        media_paths,
        validation_paths,
    )


def _append_registration_guard(
    content: str,
) -> str:
    if FALLBACK_MARKER in content:
        return content

    guard = f'''
{FALLBACK_MARKER}

_registered_api_paths = {{
    getattr(route, "path", None)
    for route in api_router.routes
}}

if "{MEDIA_PATH}" not in _registered_api_paths:
    api_router.include_router(
        media_router,
    )

_registered_api_paths = {{
    getattr(route, "path", None)
    for route in api_router.routes
}}

if "{VALIDATION_PATH}" not in _registered_api_paths:
    api_router.include_router(
        integration_validation_router,
    )
'''

    return content.rstrip() + "\n\n" + guard.lstrip()


def _show_import_source() -> None:
    app_module = importlib.import_module("app")

    app_file = getattr(
        app_module,
        "__file__",
        None,
    )

    print("Imported project app from:")
    print(f"  {app_file}")

    if app_file is None:
        raise RuntimeError("Imported app package has no __file__.")

    resolved = Path(app_file).resolve()

    if not resolved.is_relative_to(ROOT):
        raise RuntimeError("Python is still importing the wrong package named 'app'.")


def main() -> None:
    if not ROUTER_PATH.exists():
        raise RuntimeError(f"Router file does not exist: {ROUTER_PATH}")

    _show_import_source()

    content = ROUTER_PATH.read_text(encoding="utf-8")

    content = _ensure_import(
        content,
        module="app.api.v1.media",
        alias="media_router",
    )

    content = _ensure_import(
        content,
        module=("app.api.v1.integration_validation"),
        alias=("integration_validation_router"),
    )

    if not _has_direct_include(
        content,
        "media_router",
    ):
        content = _append_include(
            content,
            "media_router",
        )

        print("Added direct media_router inclusion.")
    else:
        print("Direct media_router inclusion already exists.")

    if not _has_direct_include(
        content,
        "integration_validation_router",
    ):
        content = _append_include(
            content,
            ("integration_validation_router"),
        )

        print("Added direct integration validation router inclusion.")
    else:
        print("Direct integration-validation inclusion already exists.")

    ROUTER_PATH.write_text(
        content,
        encoding="utf-8",
    )

    # First real import verification.
    paths = _registered_paths()

    missing = {
        path
        for path in (
            MEDIA_PATH,
            VALIDATION_PATH,
        )
        if path not in paths
    }

    if missing:
        print("")
        print("Direct includes exist but required routes are still missing.")
        print("Adding guarded final registration at the end of router.py.")

        content = ROUTER_PATH.read_text(encoding="utf-8")

        content = _append_registration_guard(content)

        ROUTER_PATH.write_text(
            content,
            encoding="utf-8",
        )

        paths = _registered_paths()

    media_source_paths, validation_source_paths = _source_router_paths()

    print("")
    print("Source media router paths:")

    for path in sorted(media_source_paths):
        print(f"  {path}")

    print("")
    print("Source integration-validation router paths:")

    for path in sorted(validation_source_paths):
        print(f"  {path}")

    print("")
    print("Final api_router verification:")

    checks = {
        MEDIA_PATH: (MEDIA_PATH in paths),
        VALIDATION_PATH: (VALIDATION_PATH in paths),
    }

    failures: list[str] = []

    for path, passed in checks.items():
        status = "PASS" if passed else "FAIL"

        print(f"  {status}: {path}")

        if not passed:
            failures.append(path)

    if failures:
        print("")
        print("Registered api_router paths:")

        for path in sorted(paths):
            print(f"  {path}")

        raise RuntimeError("Required routes are still missing: " + ", ".join(failures))

    print("")
    print("24C router registration fix applied successfully.")


if __name__ == "__main__":
    main()
