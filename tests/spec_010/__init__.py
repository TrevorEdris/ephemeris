# SPEC-010 ingest-skill body assertions describe the v0.1.x slash command
# (Bash mv, no python3 subprocess, staging_root env var, etc). v0.2.0
# rewrites the slash command to delegate to ephemeris.cli; SPEC-015 covers
# the new contract.
collect_ignore_glob = [
    "test_ingest_skill_body.py",
    "test_ingest_skill_error_handling.py",
]
