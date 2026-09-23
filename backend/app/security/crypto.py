import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from app.core.config import settings

class CryptoError(Exception):
    """Base class for cryptographic exceptions."""
    pass

class AESGCMCipher:
    """
    AES-256-GCM Authenticated Encryption with Associated Data (AEAD).
    """
    def __init__(self, base64_key: str = None):
        if not base64_key:
            base64_key = settings.FINMIND_MASTER_KEY
            
        try:
            self.key = base64.b64decode(base64_key)
        except Exception:
            raise CryptoError("Master key is not valid base64.")
            
        if len(self.key) != 32:
            raise CryptoError(f"AES-256 requires a 32-byte key. Provided key is {len(self.key)} bytes.")
            
        self.aesgcm = AESGCM(self.key)

    def encrypt(self, plaintext: str, associated_data: bytes = None) -> dict:
        """
        Encrypts plaintext using AES-GCM.
        Returns a dict containing base64 encoded strings:
        - nonce
        - ciphertext
        - tag
        """
        # AES-GCM requires a 96-bit (12-byte) unique IV/nonce per encryption operation.
        nonce = os.urandom(12)
        
        # encrypt() returns ciphertext + 16-byte auth tag appended.
        encrypted_data = self.aesgcm.encrypt(nonce, plaintext.encode('utf-8'), associated_data)
        
        # Extract ciphertext and tag
        ciphertext = encrypted_data[:-16]
        tag = encrypted_data[-16:]
        
        return {
            "nonce": base64.b64encode(nonce).decode('utf-8'),
            "ciphertext": base64.b64encode(ciphertext).decode('utf-8'),
            "tag": base64.b64encode(tag).decode('utf-8')
        }

    def decrypt(self, b64_nonce: str, b64_ciphertext: str, b64_tag: str, associated_data: bytes = None) -> str:
        """
        Decrypts AES-GCM encrypted data.
        Raises InvalidTag if tampering is detected.
        """
        try:
            nonce = base64.b64decode(b64_nonce)
            ciphertext = base64.b64decode(b64_ciphertext)
            tag = base64.b64decode(b64_tag)
        except Exception:
            raise CryptoError("Failed to base64 decode encryption parameters.")
            
        encrypted_data = ciphertext + tag
        
        try:
            plaintext = self.aesgcm.decrypt(nonce, encrypted_data, associated_data)
            return plaintext.decode('utf-8')
        except InvalidTag:
            raise CryptoError("Authentication tag validation failed. Ciphertext has been tampered with or key is incorrect.")
