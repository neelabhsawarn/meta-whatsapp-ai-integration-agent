import hashlib
import hmac
from app.security import check_signature, private_id, payload_fingerprint


def test_signature_accepts_exact_raw_bytes():
    secret = "a-secret"
    raw = b'{"hello" : "world"}'
    signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    assert check_signature(raw, signature, secret)
    assert not check_signature(b'{"hello":"world"}', signature, secret)
    assert not check_signature(raw, "sha256=abc", secret)
    assert not check_signature(raw, None, secret)
    assert not check_signature(raw, signature, "wrong")


def test_identifier_pseudonyms_do_not_contain_inputs():
    assert private_id("secret", "447000000001") == private_id("secret", "447000000001")
    assert "447000000001" not in private_id("secret", "447000000001")
    assert payload_fingerprint("secret", "447000000001", "HELLO") != payload_fingerprint("secret", "447000000001", "GOODBYE")
