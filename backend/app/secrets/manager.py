import abc
from pydantic import SecretStr
from sqlalchemy.orm import Session
from app.security.crypto import AESGCMCipher
# Note: we will import the DB models later when we build them.

class SecretManager(abc.ABC):
    @abc.abstractmethod
    def store_secret(self, db: Session, reference_alias: str, plaintext_secret: str, provider: str, created_by_id: str) -> str:
        """Stores a secret securely and returns the reference ID."""
        pass

    @abc.abstractmethod
    def get_secret(self, db: Session, reference_alias: str) -> SecretStr:
        """Retrieves and decrypts a secret, returning it wrapped in a Pydantic SecretStr."""
        pass

class LocalEncryptedSecretStore(SecretManager):
    """
    Phase 1 MVP implementation. 
    Encrypts secrets using the master key from the environment and stores them in the relational DB.
    """
    def __init__(self):
        self.cipher = AESGCMCipher()

    def store_secret(self, db: Session, reference_alias: str, plaintext_secret: str, provider: str, created_by_id: str) -> str:
        from app.models.secrets import SecretReference, EncryptedSecret
        import uuid
        
        # Check if reference already exists
        existing_ref = db.query(SecretReference).filter(SecretReference.alias == reference_alias).first()
        if existing_ref:
            ref_id = existing_ref.id
        else:
            ref_id = str(uuid.uuid4())
            new_ref = SecretReference(
                id=ref_id,
                alias=reference_alias,
                provider=provider,
                description=f"Secret for {provider}",
                created_by=created_by_id
            )
            db.add(new_ref)
            db.commit()

        # Encrypt the secret
        encrypted_data = self.cipher.encrypt(plaintext_secret)
        
        # Store encrypted payload
        enc_id = str(uuid.uuid4())
        new_enc = EncryptedSecret(
            id=enc_id,
            reference_id=ref_id,
            key_version="v1",
            iv_base64=encrypted_data["nonce"],
            tag_base64=encrypted_data["tag"],
            ciphertext_base64=encrypted_data["ciphertext"]
        )
        
        # If updating an existing secret, remove the old encrypted record first
        if existing_ref:
            db.query(EncryptedSecret).filter(EncryptedSecret.reference_id == ref_id).delete()
            
        db.add(new_enc)
        db.commit()
        return ref_id

    def get_secret(self, db: Session, reference_alias: str) -> SecretStr:
        from app.models.secrets import SecretReference, EncryptedSecret
        
        ref = db.query(SecretReference).filter(SecretReference.alias == reference_alias).first()
        if not ref:
            raise ValueError(f"Secret reference '{reference_alias}' not found.")
            
        enc = db.query(EncryptedSecret).filter(EncryptedSecret.reference_id == ref.id).first()
        if not enc:
            raise ValueError(f"Encrypted payload for '{reference_alias}' not found.")
            
        plaintext = self.cipher.decrypt(
            b64_nonce=enc.iv_base64,
            b64_ciphertext=enc.ciphertext_base64,
            b64_tag=enc.tag_base64
        )
        
        return SecretStr(plaintext)
