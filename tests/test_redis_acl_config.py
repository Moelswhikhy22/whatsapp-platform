from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_redis_start_script_disables_default_user() -> None:
    script = (ROOT / "infra" / "redis" / "start.sh").read_text(encoding="utf-8")

    assert "user default off" in script
    assert "user whatsapp-platform on" in script
    assert "#${password_hash}" in script


def test_secure_compose_override_uses_authenticated_redis_url() -> None:
    compose = (ROOT / "docker-compose.redis-secure.yml").read_text(encoding="utf-8")

    assert "redis://whatsapp-platform:${REDIS_PASSWORD}@redis:6379/0" in compose

    assert "redis://redis:6379/0" not in compose
