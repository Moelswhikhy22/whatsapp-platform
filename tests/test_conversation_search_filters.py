from __future__ import annotations

from uuid import uuid4

from app.db.models.conversation import (
    ConversationState,
)
from app.repositories.conversation_search import (
    ConversationSearchFilters,
)


def test_search_filters_support_required_admin_fields() -> None:
    conversation_id = uuid4()
    employee_id = uuid4()
    group_id = uuid4()

    filters = ConversationSearchFilters(
        search="customer",
        conversation_id=(conversation_id),
        customer="Ahmed",
        company="Example LLC",
        phone="2010",
        whatsapp_number="+966",
        responsible_employee_id=(employee_id),
        group_id=group_id,
        state=ConversationState.OPEN,
        message_text="invoice",
    )

    assert filters.conversation_id == conversation_id

    assert filters.responsible_employee_id == employee_id

    assert filters.group_id == group_id

    assert filters.state is ConversationState.OPEN

    assert filters.message_text == ("invoice")
