from dataclasses import dataclass
from typing import BinaryIO, Protocol


@dataclass(frozen=True)
class StoredObject:
    object_key: str
    content_type: str
    size_bytes: int


class PrivateObjectStorage(Protocol):
    def put_private(self, object_key: str, stream: BinaryIO, content_type: str) -> StoredObject: ...
    def create_download_url(self, object_key: str, expires_seconds: int = 300) -> str: ...


class S3CompatibleStorageNotConfigured:
    """Private S3-compatible storage boundary. Public ACLs are never requested."""

    def put_private(self, object_key: str, stream: BinaryIO, content_type: str) -> StoredObject:
        raise RuntimeError("Private object storage is not configured; file upload was not accepted")

    def create_download_url(self, object_key: str, expires_seconds: int = 300) -> str:
        raise RuntimeError("Private object storage is not configured; no download URL was created")
