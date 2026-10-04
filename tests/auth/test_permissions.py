from app.auth.permissions import Permission


def test_permission_values_are_unique() -> None:
    values = [permission.value for permission in Permission]

    assert len(values) == len(set(values))


def test_platform_permissions_are_explicitly_separated() -> None:
    platform_permissions = {
        Permission.PLATFORM_TENANT_CREATE,
        Permission.PLATFORM_TENANT_READ,
        Permission.PLATFORM_TENANT_UPDATE,
        Permission.PLATFORM_TENANT_SUSPEND,
    }

    assert all(permission.value.startswith("platform:") for permission in platform_permissions)


def test_core_conversation_permissions_exist() -> None:
    assert {
        Permission.CONVERSATION_READ,
        Permission.CONVERSATION_CLAIM,
        Permission.MESSAGE_SEND,
        Permission.CONVERSATION_CLOSE,
        Permission.CONVERSATION_REASSIGN,
        Permission.CONVERSATION_TRANSFER,
        Permission.CONVERSATION_ESCALATE,
    }
