import os
from abc import ABC, abstractmethod
from typing import Optional

class SecretProvider(ABC):
    """
    Abstract Secret Provider Interface.
    Allows hot-swapping secret sources (Env, Vault, KMS) without refactoring the application logic.
    """
    @abstractmethod
    def get_secret(self, key: str) -> Optional[str]:
        pass

class EnvSecretManager(SecretProvider):
    """
    Production MVP Implementation.
    Fetches keys from os.environ (which is populated by .env).
    """
    def get_secret(self, key: str) -> Optional[str]:
        return os.getenv(key)

class VaultSecretManager(SecretProvider):
    """
    Stub Adapter for HashiCorp Vault.
    Demonstrates how Enterprise KMS integration would plug into the interface.
    """
    def __init__(self, vault_url: str, token: str):
        self.vault_url = vault_url
        self.token = token
        
    def get_secret(self, key: str) -> Optional[str]:
        # In a real implementation, this would make an authenticated HTTP request to Vault
        # e.g., response = requests.get(f"{self.vault_url}/v1/secret/data/{key}", headers={"X-Vault-Token": self.token})
        # return response.json()["data"]["data"]["value"]
        raise NotImplementedError("Vault integration is planned for a future enterprise phase.")

# Global Singleton for the current provider
# In a robust DI container (like FastAPI Depends), this could be injected. 
# For now, we instantiate the configured provider globally.
secret_manager: SecretProvider = EnvSecretManager()

def get_secret(key: str) -> Optional[str]:
    """Helper function to fetch a secret from the active provider."""
    return secret_manager.get_secret(key)
