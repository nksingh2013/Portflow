from typing import Protocol


class OAuthIdentity(Protocol):
    subject: str
    email: str
    email_verified: bool
    display_name: str


class OAuthProvider(Protocol):
    async def authenticate(self, authorization_code: str, redirect_uri: str) -> OAuthIdentity: ...


class GoogleOAuthNotConfigured:
    async def authenticate(self, authorization_code: str, redirect_uri: str) -> OAuthIdentity:
        raise RuntimeError("Google OAuth is not configured; add credentials and provider contract tests first")
