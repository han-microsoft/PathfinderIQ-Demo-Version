"""Search tool package — Azure AI Search backend.

Exports search functions for runbooks, tickets, equipment, and infra specs.
"""

from tools.search._azureaisearch_runbooks import search_runbooks  # noqa: F401
from tools.search._azureaisearch_tickets import search_tickets  # noqa: F401
from tools.search._azureaisearch_equipment import search_equipment  # noqa: F401
from tools.search._azureaisearch_infra_specs import search_infra_specs  # noqa: F401

__all__ = ["search_runbooks", "search_tickets", "search_equipment", "search_infra_specs"]
