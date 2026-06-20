"""agentkit.cloud.credentials — domain-blind Azure credential factory.

Module role:
    Single source for the best-available Azure ``TokenCredential`` in the
    current environment. Three-tier resolution:

        1. **Explicit service principal** (when a caller passes
           ``service_principal=(tenant_id, client_id, client_secret)`` with all
           three non-empty) → ``ClientSecretCredential``. Used for cross-tenant
           access. The factory is domain-blind: it never reads which *named*
           service the SP belongs to — the consumer supplies the triple at the
           call boundary. (GridIQ's Fabric-SP wrapper lives in
           ``foundation/credentials.py`` and passes its ``settings.fabric_*``.)
        2. **Managed identity in Azure** (``running_in_azure()`` true) →
           ``DefaultAzureCredential``.
        3. **Local development** → ``AzureCliCredential`` (``az login``).

    The result is cached at module level, keyed by the SP tenant id (or empty),
    so repeated calls with the same shape reuse one credential. Safe in the
    async single-thread model.

Layer rule:
    stdlib + ``agentkit.config`` only (for ``running_in_azure``). ``azure.identity``
    is imported lazily so importing this module never requires the ``azure``
    extra; only *calling* ``get_azure_credential`` does.
"""

from __future__ import annotations

import logging

from agentkit.config import running_in_azure

logger = logging.getLogger(__name__)

# Module-level cache — one credential per SP-tenant configuration.
_cached_credential = None
_cached_credential_key: str = "\x00unset"


def get_azure_credential(
    *,
    service_principal: tuple[str, str, str] | None = None,
):
    """Return the best available Azure credential for the current environment.

    Args:
        service_principal: Optional ``(tenant_id, client_id, client_secret)``
            triple. When supplied with all three non-empty, tier 1 builds a
            ``ClientSecretCredential`` for cross-tenant access. ``None`` (or any
            empty member) skips tier 1 and resolves managed identity / CLI.

    Returns:
        A ``TokenCredential`` instance suitable for Azure SDK calls.

    Side effects:
        Caches the credential at module level, keyed by the SP tenant id, so
        the same shape reuses one credential. Logs the selected credential type.
    """
    global _cached_credential, _cached_credential_key

    sp_tenant = service_principal[0] if service_principal else ""
    # Cache key includes whether an SP was requested so we never hand back SP
    # creds to a caller that did not ask for them, and vice versa.
    cache_key = f"sp={sp_tenant}" if service_principal else "default"
    if _cached_credential is not None and _cached_credential_key == cache_key:
        return _cached_credential

    # Lazy import — avoids import-time failure when the ``azure`` extra is absent.
    from azure.identity import (
        AzureCliCredential,
        ClientSecretCredential,
        DefaultAzureCredential,
    )

    credential = None

    # Tier 1: explicit cross-tenant service principal.
    if service_principal:
        tenant_id, client_id, client_secret = service_principal
        if tenant_id and client_id and client_secret:
            logger.debug("credentials: ClientSecretCredential (explicit SP)")
            credential = ClientSecretCredential(tenant_id, client_id, client_secret)

    # Tier 2: managed identity in Azure (App Service / AKS / Container Apps).
    if credential is None:
        if running_in_azure():
            logger.info("credentials: DefaultAzureCredential (managed identity)")
            credential = DefaultAzureCredential()
        else:
            # Tier 3: local development via az login.
            logger.info("credentials: AzureCliCredential (local dev)")
            credential = AzureCliCredential()

    _cached_credential = credential
    _cached_credential_key = cache_key
    return credential
