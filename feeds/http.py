from __future__ import annotations
import time, urllib.request, urllib.error
from dataclasses import dataclass
from typing import FrozenSet
from urllib.parse import urlsplit

USER_AGENT = "NEXUS-FC08-threat-intel/2.0 (+https://github.com/dhartwig-fc/fc-08-emerging-threat-intelligence)"
REQUEST_GAP_SECONDS = 2.0
TIMEOUT_SECONDS = 30
_last_request = [0.0]

class FetchRefused(Exception):
    pass

@dataclass(frozen=True)
class Fetched:
    url: str
    final_url: str
    content_type: str
    body: bytes

# Every source is https. A guard's local test server widens this to http; nothing else does.
ALLOWED_SCHEMES = ("https",)


def _check_host(url: str, allowed_hosts: FrozenSet[str]) -> None:
    """The allowlist is exact on scheme and netloc: an allowed host on another port, over plain http,
    or behind userinfo ("https://allowed@evil/", "https://evil@allowed/") is refused."""
    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_SCHEMES or (parts.netloc or "").lower() not in allowed_hosts:
        raise FetchRefused("%s is not on the allowlist %s" % (url, sorted(allowed_hosts)))

class _Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts):
        self.allowed_hosts = allowed_hosts
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A redirect off the allowlist is refused here, BEFORE the request to the other host is made.
        _check_host(newurl, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def get(url: str, *, allowed_hosts: FrozenSet[str], allowed_types: FrozenSet[str], max_bytes: int) -> Fetched:
    _check_host(url, allowed_hosts)
    wait = _last_request[0] + REQUEST_GAP_SECONDS - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    opener = urllib.request.build_opener(_Redirects(allowed_hosts))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener.open(req, timeout=TIMEOUT_SECONDS) as resp:
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype not in allowed_types:
                raise FetchRefused("%s answered %r, not one of %s" % (url, ctype, sorted(allowed_types)))
            body = resp.read(max_bytes + 1)
            final = resp.geturl()
    except urllib.error.URLError as exc:
        raise FetchRefused("%s could not be fetched: %s" % (url, getattr(exc, "reason", exc)))
    finally:
        _last_request[0] = time.monotonic()
    if len(body) > max_bytes:
        raise FetchRefused("%s is larger than %d bytes" % (url, max_bytes))
    _check_host(final, allowed_hosts)
    return Fetched(url, final, ctype, body)
