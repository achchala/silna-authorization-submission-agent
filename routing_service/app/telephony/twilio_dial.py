def start_outbound_call(
    *,
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_e164: str,
    voice_url: str,
    status_callback: str | None = None,
) -> str:
    from twilio.rest import Client

    client = Client(account_sid, auth_token)
    kwargs: dict = {"to": to_e164, "from_": from_number, "url": voice_url, "method": "GET"}
    if status_callback:
        kwargs["status_callback"] = status_callback
        kwargs["status_callback_event"] = ["initiated", "ringing", "answered", "completed"]
    call = client.calls.create(**kwargs)
    return str(call.sid)
