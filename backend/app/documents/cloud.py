"""Private Supabase object storage. Local paths are a disposable processing cache."""
from __future__ import annotations
import hashlib
import mimetypes
import os
from pathlib import Path, PurePosixPath
import tempfile
import threading
from urllib.parse import quote, urlsplit
import httpx
from ..config import get_settings


class StorageError(RuntimeError):
    pass


def key_for(value: str) -> str:
    value = value.replace("\\", "/")
    path = PurePosixPath(value)
    if path.is_absolute() or not value or any(part in {"..", "."} for part in value.split("/")) or ":" in value or "\x00" in value:
        raise StorageError("Invalid storage key")
    if value.startswith("."):
        raise StorageError("Private configuration cannot be stored as a document")
    return str(path)


class SupabaseStorage:
    def __init__(self):
        self.settings = get_settings()
        self.base = self.settings.supabase_url.rstrip("/") + "/storage/v1"
        self.bucket = quote(self.settings.supabase_storage_bucket, safe="")

    def request(self, method, path, *, missing_ok=False, **kwargs):
        headers = {"apikey": self.settings.supabase_service_role_key,
                   "Authorization": "Bearer " + self.settings.supabase_service_role_key}
        headers.update(kwargs.pop("headers", {}))
        try:
            response = httpx.request(method, self.base + path, headers=headers,
                                     timeout=self.settings.storage_timeout, **kwargs)
        except httpx.HTTPError:
            raise StorageError("Cloud storage is unavailable. Retry the operation.") from None
        if missing_ok and response.status_code in {400, 404}:
            # Supabase can return a JSON statusCode for missing objects.
            try:
                if str(response.json().get("statusCode")) == "404" or response.status_code == 404:
                    return None
            except ValueError:
                pass
        if not response.is_success:
            raise StorageError(f"Cloud storage request failed (HTTP {response.status_code}). Check the private bucket and backend key.")
        return response

    def bucket_info(self):
        return self.request("GET", f"/bucket/{self.bucket}").json()

    def signed_upload(self, key: str):
        result = self.request("POST", f"/object/upload/sign/{self.bucket}/{quote(key_for(key), safe='/')}", json={}).json()
        url = result.get("signedURL") or result.get("url")
        if not isinstance(url, str):
            raise StorageError("Cloud storage did not provide a signed upload URL")
        if url.startswith("/storage/v1/"):
            url = self.settings.supabase_url.rstrip("/") + url
        elif url.startswith("/"):
            url = self.base + url
        if urlsplit(url).netloc != urlsplit(self.base).netloc or not url.startswith("https://"):
            raise StorageError("Cloud storage returned an invalid upload URL")
        return url

    def put(self, key: str, data: bytes, content_type: str | None = None):
        self.request("POST", f"/object/{self.bucket}/{quote(key_for(key), safe='/')}", content=data,
                     headers={"Content-Type": content_type or mimetypes.guess_type(key)[0] or "application/octet-stream", "x-upsert": "true", "cache-control": "no-store"})

    def get(self, key: str):
        response = self.request("GET", f"/object/authenticated/{self.bucket}/{quote(key_for(key), safe='/')}", missing_ok=True)
        return response.content if response is not None else None

    def delete(self, keys: list[str]):
        for offset in range(0, len(keys), 100):
            self.request("DELETE", f"/object/{self.bucket}", json={"prefixes": [key_for(k) for k in keys[offset:offset+100]]})

    def keys(self, prefix: str) -> list[str]:
        prefix = key_for(prefix).rstrip("/")
        found, offset = [], 0
        while True:
            rows = self.request("POST", f"/object/list/{self.bucket}", json={"prefix": prefix, "limit": 100, "offset": offset, "sortBy": {"column": "name", "order": "asc"}}).json()
            for row in rows:
                key = prefix + "/" + row["name"]
                if row.get("id") is None:
                    found.extend(self.keys(key))
                else:
                    found.append(key)
            if len(rows) < 100:
                return found
            offset += 100


_lock = threading.RLock()
_uploaded: dict[str, str] = {}


def sync_file(path: Path):
    s = get_settings()
    if s.storage_provider != "supabase" or not path.is_file():
        return
    key = key_for(path.resolve().relative_to(s.data_path).as_posix())
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    with _lock:
        if _uploaded.get(key) != digest:
            SupabaseStorage().put(key, data)
            _uploaded[key] = digest


def hydrate(path: Path):
    s = get_settings()
    if s.storage_provider != "supabase" or path.is_file():
        return path
    key = key_for(path.resolve().relative_to(s.data_path).as_posix())
    with _lock:
        if path.is_file():
            return path
        data = SupabaseStorage().get(key)
        if data is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, scratch = tempfile.mkstemp(prefix=".download-", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as file:
                    file.write(data)
                os.replace(scratch, path)
            finally:
                Path(scratch).unlink(missing_ok=True)
    return path


def remove_prefix(prefix: str, keep_reports=False):
    if get_settings().storage_provider != "supabase":
        return
    prefix = key_for(prefix).rstrip("/")
    keys = SupabaseStorage().keys(prefix)
    if keep_reports:
        keys = [k for k in keys if not k.startswith(prefix + "/reports/")]
    SupabaseStorage().delete(keys)
    with _lock:
        for key in keys:
            _uploaded.pop(key, None)


def remove_file(path: Path):
    s = get_settings()
    key = path.resolve().relative_to(s.data_path).as_posix()
    if s.storage_provider == "supabase":
        SupabaseStorage().delete([key])
        with _lock:
            _uploaded.pop(key, None)
    path.unlink(missing_ok=True)
