"""agentkit.dev_tools — headless developer/CI tooling.

Generic operator-side tools for exercising a deployed agentkit app:

    - ``dev_sign`` — local Ed25519 keypair manager + signed-request CLI for
      the devauth side-channel (zero server secrets).
    - ``sse_contract_probe`` — headless SSE event-sequence contract tester.

Both expose a ``main(argv)`` entrypoint so a consumer can ship a thin
``python3 -m agentkit.dev_tools.<tool>`` / ``scripts/<tool>.py`` CLI surface.
Imports ``agentkit.hosting`` / ``cryptography`` / stdlib only — zero consumer
(domain) imports.
"""

__all__: list[str] = []
