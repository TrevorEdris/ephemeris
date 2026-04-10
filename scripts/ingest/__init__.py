"""ephemeris ingest entry points.

Each submodule handles a single episode source:

- ``graphiti_client``: shared Graphiti setup + helpers
- ``ingest_sessions``: session artifacts → workflow-knowledge group
- ``ingest_codebase``: git log + PR bodies → codebase-history group
- ``ingest_jira``: Jira ticket enrichment invoked by ``ingest_codebase``

Runtime state (dedup, link tracking) lives at ``~/.ai/ephemeris/state/``.
"""
