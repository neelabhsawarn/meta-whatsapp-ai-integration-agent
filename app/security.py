"""Security helpers: raw-byte signature verification and keyed deduplication."""
import hashlib
import hmac
import re


def check_signature(body: bytes, signature_header: str | None, app_secret: str) -> bool:
    """Meta signs the original unmodified bytes with HMAC SHA-256."""
    if not signature_header or not re.fullmatch(r"sha256=[0-9a-fA-F]{64}", signature_header):
        return False
    digest = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest("sha256=" + digest, signature_header.lower())


def private_id(secret: str, identifier: str) -> str:
    """Stable pseudonym for events and recipient identifiers; no raw PII stored in logs."""
    return hmac.new(secret.encode(), identifier.encode(), hashlib.sha256).hexdigest()


def payload_fingerprint(secret: str, recipient: str, message: str) -> str:
    return private_id(secret, recipient + "\x00" + message)
