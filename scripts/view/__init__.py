"""Deterministic view layer over the Graphiti knowledge graph.

``render.py`` turns graph contents into browsable markdown via Jinja2 templates.
``lint.py`` runs health checks (isolated nodes, stale renders, render/graph
divergence). Both scripts avoid LLM calls in default modes — see
``docs/token-efficiency.md``.
"""
