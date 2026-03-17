"""Services package — backend business logic and infrastructure adapters.

This package contains:
    - ``llm/``                 – LLMService protocol, factory, Echo/Mock providers
        - ``llm/agent.py``     – Azure AI Agent Framework streaming provider
        - ``llm/openai.py``    – OpenAI-compatible streaming provider
    - ``conversation/``        – Token counting, sliding window, lifecycle, metadata
    - ``scenario.py``          – Scenario path resolution, YAML parsing, topology loading
    - ``session_store/``       – SessionStore protocol (interface)
        - ``session_store/memory.py``  – InMemorySessionStore (dev / fallback)
        - ``session_store/cosmos.py``  – CosmosSessionStore (production, Cosmos DB NoSQL)
"""
