from __future__ import annotations
import http.client, re, time, urllib.request, urllib.error
from dataclasses import dataclass
from typing import FrozenSet
from urllib.parse import urlsplit

USER_AGENT = "NEXUS-FC08-threat-intel/2.0 (+https://github.com/dhartwig-fc/fc-08-emerging-threat-intelligence)"
REQUEST_GAP_SECONDS = 2.0
TIMEOUT_SECONDS = 30
_last_request = [0.0]

class FetchRefused(Exception):
    pass

class BotCheck(FetchRefused):
    """The site answered a bot check (a challenge page). DETECTION ONLY: fc-08 never retries, never changes
    its user agent or headers to get past one (evals/check_no_disguised_automation.py)."""


BOT_CHECK_CODES = (403, 429, 503)
BOT_CHECK_TITLE = re.compile(r"<title[^>]*>[^<]*(Browser check|Just a moment|Attention Required)", re.I)
BODY_PEEK_BYTES = 4096
# Akamai Bot Manager answers HTTP 200 with a stub whose meta refresh carries a bm-verify token.
AKAMAI_REFRESH = re.compile(r"<meta[^>]+http-equiv=[\"']?refresh[^>]+bm-verify=", re.I)


def _is_bot_check(code: int, headers, body: bytes) -> bool:
    if code not in BOT_CHECK_CODES:
        return False
    if (headers.get("cf-mitigated") or "").strip().lower() == "challenge":
        return True
    return ("cloudflare" in (headers.get("Server") or "").lower()
            and bool(BOT_CHECK_TITLE.search(body.decode("utf-8", "replace"))))


def _is_challenge_page(headers, peek: bytes) -> bool:
    """A 200 text/html answer that is a challenge page: Akamai's bm-verify refresh, or Cloudflare's."""
    text = peek.decode("utf-8", "replace")
    if AKAMAI_REFRESH.search(text):
        return True
    if (headers.get("cf-mitigated") or "").strip().lower() == "challenge":
        return True
    return "cloudflare" in (headers.get("Server") or "").lower() and bool(BOT_CHECK_TITLE.search(text))


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
            resp_headers = resp.headers
    except urllib.error.HTTPError as exc:
        try:
            peek = exc.read(BODY_PEEK_BYTES)
        except (OSError, http.client.HTTPException):
            peek = b""
        if _is_bot_check(exc.code, exc.headers, peek):
            raise BotCheck("%s answered a bot check (HTTP %d); fc-08 does not get past one" % (url, exc.code))
        raise FetchRefused("%s answered HTTP %d %s" % (url, exc.code, exc.reason))
    except urllib.error.URLError as exc:
        raise FetchRefused("%s could not be fetched: %s" % (url, getattr(exc, "reason", exc)))
    except (OSError, http.client.HTTPException) as exc:
        # urllib wraps only connect-time errors in URLError. A timeout or a dropped connection while the
        # headers or the body are read (TimeoutError, RemoteDisconnected, IncompleteRead, ...) arrives
        # raw, and must still be a FetchRefused so the caller records the source as unreachable.
        raise FetchRefused("%s could not be fetched: %s: %s" % (url, type(exc).__name__, exc))
    finally:
        _last_request[0] = time.monotonic()
    if len(body) > max_bytes:
        raise FetchRefused("%s is larger than %d bytes" % (url, max_bytes))
    _check_host(final, allowed_hosts)
    if ctype == "text/html" and _is_challenge_page(resp_headers, body[:BODY_PEEK_BYTES]):
        raise BotCheck("%s answered a bot check (HTTP 200 challenge page); fc-08 does not get past one" % url)
    return Fetched(url, final, ctype, body)
