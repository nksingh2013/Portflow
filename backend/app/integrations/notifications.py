from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class NotificationRequest:
    recipient: str
    subject: str
    body: str
    metadata: dict[str, str]


class NotificationProvider(Protocol):
    async def send(self, request: NotificationRequest) -> str: ...


class ProviderNotConfigured:
    def __init__(self, channel: str):
        self.channel = channel

    async def send(self, request: NotificationRequest) -> str:
        raise RuntimeError(f"{self.channel} delivery is not configured; no message was sent")


email_provider = ProviderNotConfigured("Email")
sms_provider = ProviderNotConfigured("SMS")
whatsapp_provider = ProviderNotConfigured("WhatsApp")
