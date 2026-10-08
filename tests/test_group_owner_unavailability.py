from app.db.models.group import (
    Group,
    OwnerUnavailablePolicy,
)


def test_owner_unavailability_policy_catalog() -> None:
    assert set(OwnerUnavailablePolicy) == {
        OwnerUnavailablePolicy.KEEP_OWNER,
        OwnerUnavailablePolicy.RETURN_TO_QUEUE,
        OwnerUnavailablePolicy.AUTO_REASSIGN,
        OwnerUnavailablePolicy.NOTIFY_ADMIN,
    }


def test_group_has_owner_unavailability_settings() -> None:
    columns = Group.__table__.columns

    assert "owner_unavailable_policy" in columns
    assert "offline_grace_seconds" in columns

    assert columns["owner_unavailable_policy"].nullable is False

    assert columns["offline_grace_seconds"].nullable is False
