from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

APP = ROOT / "app"
TESTS = ROOT / "tests"


def _relative(path: Path) -> str:
    return str(
        path.relative_to(ROOT)
    ).replace("\\", "/")


def _search_files(
    root: Path,
    needles: tuple[str, ...],
) -> list[Path]:
    matches: list[Path] = []

    for path in root.rglob("*.py"):
        try:
            content = path.read_text(
                encoding="utf-8",
            )
        except UnicodeDecodeError:
            continue

        if any(
            needle in content
            for needle in needles
        ):
            matches.append(path)

    return sorted(matches)


def _show_file(
    path: Path,
) -> None:
    print()
    print(
        "=" * 80
    )
    print(
        _relative(path)
    )
    print(
        "=" * 80
    )

    print(
        path.read_text(
            encoding="utf-8",
        )
    )


def _show_matches(
    title: str,
    paths: list[Path],
) -> None:
    print()
    print(
        f"### {title}"
    )

    if not paths:
        print(
            "NONE"
        )
        return

    for path in paths:
        print(
            f"- {_relative(path)}"
        )


def inspect_media() -> None:
    media_files = _search_files(
        APP,
        (
            "media.process",
            "MediaObject(",
            "MediaObjectRepository",
            "provider_media_id",
            "generate_presigned",
            "presigned_url",
        ),
    )

    _show_matches(
        "MEDIA-RELATED FILES",
        media_files,
    )

    likely_worker_files: list[Path] = []

    for path in media_files:
        content = path.read_text(
            encoding="utf-8",
        )

        if (
            "media.process" in content
            or (
                "provider_media_id" in content
                and (
                    "MediaObject" in content
                    or "put_object" in content
                    or "upload" in content
                    or "download" in content
                )
            )
        ):
            likely_worker_files.append(
                path
            )

    _show_matches(
        "LIKELY MEDIA PROCESSING FILES",
        likely_worker_files,
    )

    for path in likely_worker_files:
        _show_file(path)


def inspect_cookie_security() -> None:
    cookie_files = _search_files(
        APP,
        (
            "SESSION_COOKIE_NAME",
            "load_session_cookie_config",
            "set_cookie(",
            "delete_cookie(",
            "httponly",
            "samesite",
        ),
    )

    _show_matches(
        "SESSION / COOKIE FILES",
        cookie_files,
    )

    for path in cookie_files:
        if (
            "/auth/" in _relative(path)
            or _relative(path).endswith(
                "app/api/auth.py"
            )
        ):
            _show_file(path)


def inspect_presigned_url_logging() -> None:
    suspicious_files: list[Path] = []

    for path in APP.rglob("*.py"):
        content = path.read_text(
            encoding="utf-8"
        )

        lower = content.lower()

        if (
            "presigned" in lower
            and (
                "logger." in lower
                or "logging." in lower
                or "print(" in lower
            )
        ):
            suspicious_files.append(
                path
            )

    _show_matches(
        "POTENTIAL PRESIGNED URL LOGGING",
        suspicious_files,
    )


def inspect_env_files() -> None:
    print()
    print(
        "### ENV FILES"
    )

    env_files = sorted(
        path
        for path in ROOT.glob(".env*")
        if path.is_file()
    )

    if not env_files:
        print(
            "NONE"
        )
        return

    for path in env_files:
        print(
            f"- {_relative(path)}"
        )

        if path.name.endswith(
            ".example"
        ):
            _show_file(path)


def inspect_tenant_secret_env_usage() -> None:
    suspicious_terms = (
        "META_ACCESS_TOKEN",
        "META_APP_SECRET",
        "WHATSAPP_ACCESS_TOKEN",
        "WHATSAPP_APP_SECRET",
        "ODOO_API_KEY",
        "TENANT_API_KEY",
        "TENANT_SECRET",
    )

    matches: list[
        tuple[Path, str]
    ] = []

    for path in APP.rglob("*.py"):
        content = path.read_text(
            encoding="utf-8",
        )

        for term in suspicious_terms:
            if term in content:
                matches.append(
                    (
                        path,
                        term,
                    )
                )

    print()
    print(
        "### TENANT SECRET ENV USAGE"
    )

    if not matches:
        print(
            "NONE"
        )
        return

    for path, term in matches:
        print(
            f"- {_relative(path)}: "
            f"{term}"
        )


def inspect_security_tests() -> None:
    files = _search_files(
        TESTS,
        (
            "httponly",
            "samesite",
            "secure",
            "presigned",
            "MediaObject",
            "media.process",
        ),
    )

    _show_matches(
        "EXISTING SECURITY-RELATED TESTS",
        files,
    )


def main() -> None:
    print(
        "SECTION 25B SECURITY INSPECTION"
    )
    print(
        f"Project root: {ROOT}"
    )

    inspect_media()
    inspect_cookie_security()
    inspect_presigned_url_logging()
    inspect_env_files()
    inspect_tenant_secret_env_usage()
    inspect_security_tests()


if __name__ == "__main__":
    main()