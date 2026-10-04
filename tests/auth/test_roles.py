from app.auth.roles import HUMAN_ROLES, MACHINE_ROLES, Role


def test_supported_roles_are_stable() -> None:
    assert {role.value for role in Role} == {
        "platform_admin",
        "tenant_admin",
        "group_admin",
        "employee",
        "integration",
    }


def test_integration_is_machine_only_role() -> None:
    assert frozenset({Role.INTEGRATION}) == MACHINE_ROLES
    assert Role.INTEGRATION not in HUMAN_ROLES


def test_human_roles_do_not_include_integration() -> None:
    assert (
        frozenset(
            {
                Role.PLATFORM_ADMIN,
                Role.TENANT_ADMIN,
                Role.GROUP_ADMIN,
                Role.EMPLOYEE,
            }
        )
        == HUMAN_ROLES
    )
