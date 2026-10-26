"""Create synthetic, privacy-safe incidents for offline practice (NO Meta calls)."""
from .config import Settings
from .db import Ledger


def main() -> None:
    db = Ledger(Settings.from_env().database_path)
    for source, event_type, code, hint, attempt in [
        ("meta", "rate_limited", "130429", "Meta rate limit; backoff before retry", 1),
        ("meta", "rate_limited", "130429", "Meta rate limit; backoff before retry", 2),
        ("webhook", "authentication_failure", "bad_signature", "HMAC SHA-256 verification failed", 0),
        ("meta", "permanent_api_error", "190", "Check permissions, recipient, token, template and test access", 1),
    ]:
        db.log(source, event_type, code, hint, attempt)
    print("Inserted 4 synthetic diagnostic rows. No network or Meta calls made.")


if __name__ == "__main__":
    main()
