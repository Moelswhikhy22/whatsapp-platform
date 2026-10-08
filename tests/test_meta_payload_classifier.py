from app.integrations.meta.payload_classifier import (
    classify_meta_payload,
)


def test_detects_messages() -> None:
    result = classify_meta_payload(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "id": "wamid.1",
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    )

    assert result.has_messages is True
    assert result.has_statuses is False
    assert result.has_message_echoes is False


def test_detects_statuses() -> None:
    result = classify_meta_payload(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {
                                        "id": "wamid.1",
                                        "status": "delivered",
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    )

    assert result.has_messages is False
    assert result.has_statuses is True
    assert result.has_message_echoes is False


def test_detects_message_echoes() -> None:
    result = classify_meta_payload(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "field": "smb_message_echoes",
                            "value": {
                                "message_echoes": [
                                    {
                                        "id": "wamid.echo.1",
                                    }
                                ]
                            },
                        }
                    ]
                }
            ]
        }
    )

    assert result.has_messages is False
    assert result.has_statuses is False
    assert result.has_message_echoes is True


def test_message_echoes_require_correct_field() -> None:
    result = classify_meta_payload(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "message_echoes": [
                                    {
                                        "id": "wamid.echo.1",
                                    }
                                ]
                            },
                        }
                    ]
                }
            ]
        }
    )

    assert result.has_message_echoes is False


def test_detects_mixed_payload() -> None:
    result = classify_meta_payload(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "id": "wamid.1",
                                    }
                                ],
                                "statuses": [
                                    {
                                        "id": "wamid.2",
                                    }
                                ],
                            }
                        },
                        {
                            "field": "smb_message_echoes",
                            "value": {
                                "message_echoes": [
                                    {
                                        "id": "wamid.echo.1",
                                    }
                                ]
                            },
                        },
                    ]
                }
            ]
        }
    )

    assert result.has_messages is True
    assert result.has_statuses is True
    assert result.has_message_echoes is True
