import secrets


def get_shared_auth_token(context, settings: dict) -> str:
    """Gets the auth token from settings or context, or generates a shared one."""
    token = settings.get("auth_token")
    if token:
        return token
    token = context.get("shared_auth_token")
    if not token:
        token = secrets.token_urlsafe(32)
        context.set("shared_auth_token", token)
    return token
