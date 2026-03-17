#!/usr/bin/env python3
"""Deploy documents to Azure AI Search indices.

Usage:
    python3 scripts/deploy_search.py --scenario-dir data/scenarios/telecom-playground-v2
    python3 scripts/deploy_search.py --manifest data/scenarios/telecom-playground-v2/search_manifest.yaml --upload-files
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from azureaisearch.provision_search_index import main

if __name__ == "__main__":
    sys.exit(main())
