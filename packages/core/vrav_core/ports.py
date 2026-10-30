"""Port interfaces (Protocols)."""
from typing import Protocol, AsyncIterator, Any
from decimal import Decimal


class AIProvider(Protocol):
    id: str
    supports_streaming: bool
    supports_tools: bool
    supports_structured_output: bool

    async def chat(self, request: Any) -> Any: ...
    async def stream_chat(self, request: Any) -> AsyncIterator[Any]: ...


class PaymentProvider(Protocol):
    id: str

    async def create_checkout(self, req: Any) -> Any: ...
    async def handle_webhook(self, payload: bytes, signature: str | None) -> Any: ...
    async def refund(self, provider_payment_id: str, amount: Decimal, currency: str) -> Any: ...


class StorageProvider(Protocol):
    async def put(self, key: str, data: Any, content_type: str | None = None) -> Any: ...
    async def get(self, key: str) -> Any: ...
    async def delete(self, key: str) -> None: ...
    async def signed_url(self, key: str, ttl_seconds: int = 3600) -> str: ...


class LicenseVerifier(Protocol):
    async def verify(
        self,
        license_key: str,
        installation_id: str,
        machine_fingerprint: str,
    ) -> Any: ...
