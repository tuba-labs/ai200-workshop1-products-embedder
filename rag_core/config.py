"""Only the App Configuration endpoint/label and identity bootstrap via env."""
from dataclasses import dataclass
import os

from azure.appconfiguration import AzureAppConfigurationClient
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient


@dataclass(frozen=True)
class Settings:
    values: dict
    credential: object
    password: str

    def integer(self, key, low, high):
        value = int(self.values[key])
        if not low <= value <= high:
            raise ValueError(f"Setting {key} must be between {low} and {high}")
        return value

    def connect(self):
        import psycopg
        return psycopg.connect(
            host=self.values['pg-host'], dbname=self.values['pg-database'],
            user=self.values['pg-user'], password=self.password,
            sslmode='require', connect_timeout=15, autocommit=True,
        )


def load_settings():
    # Workload identity on AKS; user-assigned managed identity on Functions.
    credential = DefaultAzureCredential(managed_identity_client_id=os.getenv('AZURE_CLIENT_ID'))
    client = AzureAppConfigurationClient(os.environ['APP_CONFIG_ENDPOINT'], credential)
    label = os.getenv('APP_CONFIG_LABEL', 'workshop')
    values = {item.key.removeprefix('rag:'): item.value
              for item in client.list_configuration_settings(key_filter='rag:*', label_filter=label)}
    if int(values['embedding-dimensions']) != 1536:
        raise ValueError('This schema requires 1536 dimensions; do not change the model without reindexing.')
    secret = SecretClient(values['key-vault-uri'], credential).get_secret('postgres-password')
    return Settings(values, credential, secret.value)
