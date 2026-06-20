"""agentkit.cloud — Azure credential factory (domain-blind).

Public surface: ``from agentkit.cloud import get_azure_credential``.

Requires the ``azure`` extra (``pip install agentkit[azure]``) for
``azure-identity``. The factory is import-light — ``azure.identity`` is
imported lazily inside the call so the package imports without the extra.
"""

from agentkit.cloud.credentials import get_azure_credential

__all__ = ["get_azure_credential"]
