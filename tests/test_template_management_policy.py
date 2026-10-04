from __future__ import annotations

from uuid import UUID

import pytest

from app.authorization import (
    AuthorizationContext,
    AuthorizationDeniedError,
    Role,
    TemplateAccessResource,
    TemplateAction,
    TemplateType,
    TenantIsolationError,
    can_manage_templates,
)

TENANT_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

TENANT_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def make_template(
    *,
    tenant_id: UUID = TENANT_A_ID,
    template_type: TemplateType = TemplateType.INTERNAL,
) -> TemplateAccessResource:
    return TemplateAccessResource(
        tenant_id=tenant_id,
        template_type=template_type,
    )


def test_tenant_admin_can_read_internal_template() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_templates(
        context,
        make_template(),
        TemplateAction.READ,
    )


def test_tenant_admin_can_create_internal_template() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_templates(
        context,
        make_template(),
        TemplateAction.CREATE,
    )


def test_tenant_admin_can_update_internal_template() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_templates(
        context,
        make_template(),
        TemplateAction.UPDATE,
    )


def test_tenant_admin_can_send_internal_template() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_templates(
        context,
        make_template(),
        TemplateAction.SEND,
    )


def test_tenant_admin_can_create_meta_template() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_templates(
        context,
        make_template(
            template_type=TemplateType.META,
        ),
        TemplateAction.CREATE,
    )


def test_tenant_admin_can_update_meta_template() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_templates(
        context,
        make_template(
            template_type=TemplateType.META,
        ),
        TemplateAction.UPDATE,
    )


def test_tenant_admin_can_submit_meta_template() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_templates(
        context,
        make_template(
            template_type=TemplateType.META,
        ),
        TemplateAction.SUBMIT,
    )


def test_internal_template_cannot_be_submitted() -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert not can_manage_templates(
        context,
        make_template(
            template_type=TemplateType.INTERNAL,
        ),
        TemplateAction.SUBMIT,
    )


def test_group_admin_can_read_template() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-123",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_templates(
        context,
        make_template(),
        TemplateAction.READ,
    )


def test_group_admin_can_create_template() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-123",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_templates(
        context,
        make_template(),
        TemplateAction.CREATE,
    )


def test_group_admin_can_update_template() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-123",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_templates(
        context,
        make_template(),
        TemplateAction.UPDATE,
    )


def test_group_admin_can_send_template() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-123",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_templates(
        context,
        make_template(),
        TemplateAction.SEND,
    )


def test_group_admin_cannot_submit_meta_template() -> None:
    context = AuthorizationContext(
        actor_id="group-admin-123",
        role=Role.GROUP_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_manage_templates(
            context,
            make_template(
                template_type=TemplateType.META,
            ),
            TemplateAction.SUBMIT,
        )


def test_employee_can_read_template() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_templates(
        context,
        make_template(),
        TemplateAction.READ,
    )


def test_employee_can_send_template() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    assert can_manage_templates(
        context,
        make_template(),
        TemplateAction.SEND,
    )


def test_employee_cannot_create_template() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_manage_templates(
            context,
            make_template(),
            TemplateAction.CREATE,
        )


def test_employee_cannot_update_template() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_manage_templates(
            context,
            make_template(),
            TemplateAction.UPDATE,
        )


def test_employee_cannot_submit_meta_template() -> None:
    context = AuthorizationContext(
        actor_id="employee-123",
        role=Role.EMPLOYEE,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_manage_templates(
            context,
            make_template(
                template_type=TemplateType.META,
            ),
            TemplateAction.SUBMIT,
        )


def test_integration_cannot_read_template() -> None:
    context = AuthorizationContext(
        actor_id="integration-tenant-a",
        role=Role.INTEGRATION,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_manage_templates(
            context,
            make_template(),
            TemplateAction.READ,
        )


def test_integration_cannot_send_template() -> None:
    context = AuthorizationContext(
        actor_id="integration-tenant-a",
        role=Role.INTEGRATION,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_manage_templates(
            context,
            make_template(),
            TemplateAction.SEND,
        )


def test_platform_admin_has_no_implicit_template_access() -> None:
    context = AuthorizationContext(
        actor_id="platform-admin-123",
        role=Role.PLATFORM_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(AuthorizationDeniedError):
        can_manage_templates(
            context,
            make_template(),
            TemplateAction.READ,
        )


def test_foreign_template_is_rejected_before_rbac() -> None:
    context = AuthorizationContext(
        actor_id="integration-tenant-a",
        role=Role.INTEGRATION,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(TenantIsolationError):
        can_manage_templates(
            context,
            make_template(
                tenant_id=TENANT_B_ID,
            ),
            TemplateAction.READ,
        )


@pytest.mark.parametrize(
    "action",
    [
        TemplateAction.READ,
        TemplateAction.CREATE,
        TemplateAction.UPDATE,
        TemplateAction.SUBMIT,
        TemplateAction.SEND,
    ],
)
def test_tenant_admin_cannot_manage_foreign_tenant_template(
    action: TemplateAction,
) -> None:
    context = AuthorizationContext(
        actor_id="tenant-admin-123",
        role=Role.TENANT_ADMIN,
        tenant_id=TENANT_A_ID,
    )

    with pytest.raises(TenantIsolationError):
        can_manage_templates(
            context,
            make_template(
                tenant_id=TENANT_B_ID,
                template_type=TemplateType.META,
            ),
            action,
        )
