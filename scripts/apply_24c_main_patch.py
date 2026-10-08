from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "app" / "main.py"

IMPORT_LINE = (
    "from app.middleware.session_rate_limit import "
    "HumanSessionRateLimitMiddleware"
)

MIDDLEWARE_CALL = (
    "    application.add_middleware(\n"
    "        HumanSessionRateLimitMiddleware,\n"
    "    )\n"
)


def main() -> None:
    content = MAIN_PATH.read_text(
        encoding="utf-8"
    )

    if IMPORT_LINE not in content:
        lines = content.splitlines()

        insertion_index = None

        for index, line in enumerate(lines):
            if line.startswith("from app."):
                insertion_index = index
                break

        if insertion_index is None:
            raise RuntimeError(
                "Could not find app import section "
                "in app/main.py."
            )

        lines.insert(
            insertion_index,
            IMPORT_LINE,
        )

        content = "\n".join(lines) + "\n"

    if (
        "application.add_middleware("
        "HumanSessionRateLimitMiddleware"
        in content.replace("\n", "")
    ):
        MAIN_PATH.write_text(
            content,
            encoding="utf-8",
        )
        print(
            "HumanSessionRateLimitMiddleware "
            "already configured."
        )
        return

    marker = "    application = FastAPI("

    start = content.find(
        marker
    )

    if start == -1:
        raise RuntimeError(
            "Could not find FastAPI construction "
            "inside create_app()."
        )

    search_from = start + len(marker)

    closing = content.find(
        "\n    )",
        search_from,
    )

    if closing == -1:
        raise RuntimeError(
            "Could not find the end of "
            "FastAPI construction."
        )

    insert_at = closing + len(
        "\n    )"
    )

    content = (
        content[:insert_at]
        + "\n\n"
        + MIDDLEWARE_CALL.rstrip("\n")
        + content[insert_at:]
    )

    MAIN_PATH.write_text(
        content,
        encoding="utf-8",
    )

    print(
        "HumanSessionRateLimitMiddleware "
        "added to app/main.py."
    )


if __name__ == "__main__":
    main()
