"""Read-only fetch helper for 可影 Supabase storage. Loads creds from my-stage-hk env
files into memory only; never prints/logs/writes them. GET requests only."""
from __future__ import annotations
import json, os, re, ssl, urllib.request, urllib.parse, urllib.error
from pathlib import Path

STAGE_HK = Path(os.environ.get("MY_STAGE_HK", "/Users/wangjianzheng/Project/HG/my-stage-hk"))


def load_env(name: str) -> dict:
    d = {}
    for line in (STAGE_HK / name).read_text().splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if m:
            d[m[1]] = m[2].strip().strip('"\'')
    return d


class Client:
    def __init__(self, envfile: str):
        e = load_env(envfile)
        self.envfile = envfile
        self.base = (os.environ.get("OFFICIAL_PULL_BASE") or e["NEXT_PUBLIC_SUPABASE_URL"]).rstrip("/")
        self._key = e["NEXT_PUBLIC_SUPABASE_ANON_KEY"]
        self.host = urllib.parse.urlparse(self.base).netloc
        self.ctx = ssl.create_default_context()

    def _req(self, url: str):
        r = urllib.request.Request(url, method="GET", headers={
            "apikey": self._key, "Authorization": "Bearer " + self._key})
        if self.base.startswith("https://"):
            return urllib.request.urlopen(r, timeout=180, context=self.ctx)
        return urllib.request.urlopen(r, timeout=180)

    def get_object(self, bucket: str, key: str) -> bytes:
        """Download one object by explicit key. Raises RuntimeError with a redacted message."""
        if "customer_asset" in bucket or key.startswith("customer_asset"):
            raise RuntimeError("refusing customer_asset")
        url = f"{self.base}/storage/v1/object/{bucket}/{urllib.parse.quote(key, safe="/")}"
        try:
            with self._req(url) as resp:
                return resp.read()
        except urllib.error.HTTPError as ex:
            body = ex.read()[:300].decode("utf-8", "replace")
            raise RuntimeError(f"HTTP {ex.code} for {bucket}/{key}: {body}") from None
        except Exception as ex:  # noqa: BLE001
            raise RuntimeError(f"{type(ex).__name__} for {bucket}/{key}: {str(ex)[:200]}") from None

    def get_allowlisted_object(self, full_key: str, allowlist: set[str]) -> bytes:
        """GET one object whose full `bucket/key` is in an explicit allowlist.
        Used only for the approved missing customer_asset GLBs. Still refuses
        anything not in the allowlist and never lists a bucket."""
        if full_key not in allowlist:
            raise RuntimeError(f"refusing key not in allowlist: {full_key[:80]}")
        if ".." in full_key or full_key.endswith("/"):
            raise RuntimeError("refusing unsafe key")
        bucket, _, key = full_key.partition("/")
        if not bucket or not key:
            raise RuntimeError("invalid key")
        url = f"{self.base}/storage/v1/object/{bucket}/{urllib.parse.quote(key, safe='/')}"
        try:
            with self._req(url) as resp:
                return resp.read()
        except urllib.error.HTTPError as ex:
            body = ex.read()[:300].decode("utf-8", "replace")
            raise RuntimeError(f"HTTP {ex.code} for {bucket}/{key}: {body}") from None
        except Exception as ex:  # noqa: BLE001
            raise RuntimeError(f"{type(ex).__name__} for {bucket}/{key}: {str(ex)[:200]}") from None

    def select(self, table: str, query: str):
        url = f"{self.base}/rest/v1/{table}?{query}"
        try:
            with self._req(url) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as ex:
            body = ex.read()[:300].decode("utf-8", "replace")
            raise RuntimeError(f"HTTP {ex.code} for table {table}: {body}") from None
        except Exception as ex:  # noqa: BLE001
            raise RuntimeError(f"{type(ex).__name__} for table {table}: {str(ex)[:200]}") from None
