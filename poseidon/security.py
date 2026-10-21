"""Input boundaries shared by commands and persistence; never execute user input."""

import ipaddress
import re
from urllib.parse import urlsplit


def public_https_url(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 400 or re.search(r"[\s<>`\\\x00-\x1f\x7f]", value):
        raise ValueError("Use an HTTPS URL under 400 characters without whitespace.")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid URL.") from exc
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username
        or parsed.password
        or port not in (None, 443)
    ):
        raise ValueError("Use a public HTTPS URL without credentials or a custom port.")
    host = host.rstrip(".").lower()
    if "." not in host or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Use a public hostname.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in host.split(".")
        ):
            raise ValueError("Use an ASCII public hostname.") from None
    else:
        if not address.is_global:
            raise ValueError("Private and reserved addresses are not accepted.")
    return value


def text_input(value: str, maximum: int, label: str) -> str:
    value = value.strip()
    if not value or len(value) > maximum or any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise ValueError(f"{label} must contain 1–{maximum} characters without control characters.")
    return value
