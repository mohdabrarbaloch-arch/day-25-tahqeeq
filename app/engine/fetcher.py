"""Fetch a URL and reduce it to readable text.

This is the only outbound call in the whole app, so it is the only place that
needs to be paranoid. Three things are enforced here:

* **SSRF guard** — the hostname is resolved and every resulting address is
  checked against private, loopback, link-local and reserved ranges. Checking
  the string is not enough: `127.0.0.1.nip.io` resolves to loopback.
* **Byte cap** — the response is streamed and truncated at a configured limit
  rather than buffered whole.
* **Redirect cap** — redirects are followed manually so each hop is re-checked
  by the SSRF guard. `httpx`'s automatic redirects would skip that.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings


class FetchError(Exception):
    """Raised when a URL cannot be fetched for a reason the user should see."""


@dataclass(frozen=True, slots=True)
class FetchedPage:
    url: str
    final_url: str
    title: str
    text: str
    content_type: str
    truncated: bool


_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata.google.internal",
        "metadata",
    }
)

_SCRIPT_STYLE = re.compile(
    r"<(script|style|noscript|svg|iframe|object|embed)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_BLOCK_TAG = re.compile(
    r"</?(p|div|br|li|tr|h[1-6]|section|article|header|footer|blockquote|pre)\b[^>]*>",
    re.IGNORECASE,
)
_ANY_TAG = re.compile(r"<[^>]+>")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_OG_TITLE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
_ENTITY = re.compile(r"&(#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);")

_ENTITIES = {
    "amp": "&",
    "lt": "<",
    "gt": ">",
    "quot": '"',
    "apos": "'",
    "nbsp": " ",
    "mdash": "—",
    "ndash": "–",
    "hellip": "…",
    "rsquo": "’",
    "lsquo": "‘",
    "ldquo": "“",
    "rdquo": "”",
    "eacute": "é",
    "uuml": "ü",
    "ouml": "ö",
    "auml": "ä",
}


def _decode_entities(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token.startswith("#x") or token.startswith("#X"):
            try:
                return chr(int(token[2:], 16))
            except ValueError:
                return match.group(0)
        if token.startswith("#"):
            try:
                return chr(int(token[1:]))
            except ValueError:
                return match.group(0)
        return _ENTITIES.get(token.lower(), match.group(0))

    return _ENTITY.sub(replace, text)


def _is_blocked_address(address: str) -> bool:
    """True if this IP must not be fetched."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def assert_safe_url(url: str) -> None:
    """Reject anything that is not a plain public http(s) URL.

    Raises FetchError with a message safe to show a user.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise FetchError("Only http and https URLs can be fetched.")
    host = (parsed.hostname or "").lower()
    if not host:
        raise FetchError("That URL has no hostname.")
    if host in _BLOCKED_HOSTNAMES:
        raise FetchError("That host is not allowed.")

    # A literal IP is checked directly; a name is resolved first.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if _is_blocked_address(str(literal)):
            raise FetchError("That address is not allowed.")
        return

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve {host}.") from exc

    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise FetchError(f"Could not resolve {host}.")
    for address in addresses:
        if _is_blocked_address(address):
            raise FetchError("That host resolves to a private address, which is not allowed.")


def html_to_text(html: str) -> tuple[str, str]:
    """Strip HTML down to (title, readable text)."""
    title = ""
    for pattern in (_OG_TITLE, _H1, _TITLE):
        match = pattern.search(html)
        if match:
            candidate = _decode_entities(_ANY_TAG.sub("", match.group(1))).strip()
            if candidate:
                title = " ".join(candidate.split())
                break

    body = _COMMENT.sub(" ", html)
    body = _SCRIPT_STYLE.sub(" ", body)
    body = _BLOCK_TAG.sub("\n\n", body)
    body = _ANY_TAG.sub(" ", body)
    body = _decode_entities(body)

    lines = [" ".join(line.split()) for line in body.split("\n")]
    paragraphs = [line for line in lines if line]
    text = "\n\n".join(paragraphs)
    return title, text


def fetch_page(url: str) -> FetchedPage:
    """Fetch a URL, following redirects manually with the guard on each hop."""
    if not settings.allow_url_fetch:
        raise FetchError("URL fetching is disabled on this deployment.")

    current = url
    headers = {
        "User-Agent": "Tahqeeq/1.0 (+https://github.com/mohdabrarbaloch-arch/day-25-tahqeeq)",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
        "Accept-Language": "en-US,en;q=0.9",
    }

    with httpx.Client(
        timeout=settings.url_fetch_timeout_seconds,
        follow_redirects=False,
        headers=headers,
    ) as client:
        for _ in range(settings.url_fetch_max_redirects + 1):
            assert_safe_url(current)
            try:
                with client.stream("GET", current) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("The server redirected without a destination.")
                        current = urljoin(current, location)
                        continue

                    if response.status_code >= 400:
                        raise FetchError(f"The page returned HTTP {response.status_code}.")

                    content_type = response.headers.get("content-type", "").split(";")[0].strip()
                    if content_type and not (
                        content_type.startswith("text/")
                        or content_type in {"application/xhtml+xml", "application/xml"}
                    ):
                        raise FetchError(f"That URL is {content_type}, not a readable page.")

                    chunks: list[bytes] = []
                    total = 0
                    truncated = False
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > settings.url_fetch_max_bytes:
                            remaining = settings.url_fetch_max_bytes - (total - len(chunk))
                            if remaining > 0:
                                chunks.append(chunk[:remaining])
                            truncated = True
                            break
                        chunks.append(chunk)

                    raw = b"".join(chunks)
                    encoding = response.encoding or "utf-8"
                    try:
                        decoded = raw.decode(encoding, errors="replace")
                    except LookupError:
                        decoded = raw.decode("utf-8", errors="replace")

                    title, text = html_to_text(decoded)
                    if len(text) < settings.min_text_chars:
                        raise FetchError(
                            "That page had almost no readable text — it may need JavaScript."
                        )

                    return FetchedPage(
                        url=url,
                        final_url=current,
                        title=title,
                        text=text,
                        content_type=content_type or "text/html",
                        truncated=truncated,
                    )
            except httpx.TimeoutException as exc:
                raise FetchError("The page took too long to respond.") from exc
            except httpx.HTTPError as exc:
                raise FetchError(f"Could not fetch that page: {exc.__class__.__name__}.") from exc

    raise FetchError("Too many redirects.")
