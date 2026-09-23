import pytest
import base64
from cryptography.exceptions import InvalidTag
from app.security.crypto import AESGCMCipher, CryptoError

def test_crypto_round_trip():
    cipher = AESGCMCipher()
    plaintext = "super_secret_api_key_123"
    
    # Encrypt
    encrypted_payload = cipher.encrypt(plaintext)
    assert "nonce" in encrypted_payload
    assert "ciphertext" in encrypted_payload
    assert "tag" in encrypted_payload
    
    # Decrypt
    decrypted = cipher.decrypt(
        b64_nonce=encrypted_payload["nonce"],
        b64_ciphertext=encrypted_payload["ciphertext"],
        b64_tag=encrypted_payload["tag"]
    )
    
    assert decrypted == plaintext

def test_tamper_detection():
    cipher = AESGCMCipher()
    plaintext = "super_secret_api_key_123"
    encrypted_payload = cipher.encrypt(plaintext)
    
    # Tamper with the ciphertext (change the first byte)
    raw_ciphertext = base64.b64decode(encrypted_payload["ciphertext"])
    tampered_ciphertext = (bytes([raw_ciphertext[0] ^ 1]) + raw_ciphertext[1:])
    tampered_b64 = base64.b64encode(tampered_ciphertext).decode('utf-8')
    
    with pytest.raises(CryptoError) as exc_info:
        cipher.decrypt(
            b64_nonce=encrypted_payload["nonce"],
            b64_ciphertext=tampered_b64,
            b64_tag=encrypted_payload["tag"]
        )
    assert "Authentication tag validation failed" in str(exc_info.value)

def test_nonce_uniqueness():
    cipher = AESGCMCipher()
    nonces = set()
    # Test 100 encryptions for uniqueness (to save time in test suite instead of 10000)
    for _ in range(100):
        enc = cipher.encrypt("test")
        assert enc["nonce"] not in nonces
        nonces.add(enc["nonce"])
