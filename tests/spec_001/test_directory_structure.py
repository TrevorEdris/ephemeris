"""Step 4 — Plugin directory structure completeness.

Asserts:
- skills/ directory exists under repo root
- agents/ directory exists under repo root
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent


def test_skills_directory_exists() -> None:
    skills_dir = REPO_ROOT / "skills"
    assert skills_dir.is_dir(), f"Expected skills/ directory at {skills_dir}"


def test_agents_directory_exists() -> None:
    agents_dir = REPO_ROOT / "agents"
    assert agents_dir.is_dir(), f"Expected agents/ directory at {agents_dir}"
