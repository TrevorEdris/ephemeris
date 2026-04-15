"""tests/spec_007/test_is_in_scope.py — SPEC-007 is_in_scope predicate tests.

Covers:
    is_in_scope: empty config (always true), include match, include non-match,
                 exclude match, exclude wins over include, ** across segments,
                 * does not cross segments, ? matches single char,
                 regex metachar escaping.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# AC-1 — empty config always allows
# ---------------------------------------------------------------------------

class TestIsInScopeEmptyConfig:
    """Empty config (no include/exclude rules) → always in scope."""

    def test_is_in_scope_empty_config_always_true(self):
        """Empty ScopeConfig → is_in_scope returns True for any path."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=[], exclude=[])
        assert is_in_scope("/any/path/here", cfg) is True

    def test_is_in_scope_empty_config_empty_cwd(self):
        """Empty cwd with empty config → True (not excluded by anything)."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=[], exclude=[])
        assert is_in_scope("", cfg) is True


# ---------------------------------------------------------------------------
# AC-2 — include match
# ---------------------------------------------------------------------------

class TestIsInScopeIncludeMatch:
    """include patterns present — only matching paths are in scope."""

    def test_is_in_scope_include_only_match_returns_true(self):
        """cwd matching an include pattern → in scope."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=["/work/**"], exclude=[])
        assert is_in_scope("/work/project/subdir", cfg) is True

    def test_is_in_scope_include_exact_match(self):
        """cwd exactly matching an include pattern without glob → in scope."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=["/work/project"], exclude=[])
        assert is_in_scope("/work/project", cfg) is True


# ---------------------------------------------------------------------------
# AC-7 — include non-match
# ---------------------------------------------------------------------------

class TestIsInScopeIncludeNonMatch:
    """cwd not matching any include pattern → out of scope."""

    def test_is_in_scope_include_only_non_match_returns_false(self):
        """cwd not matching any include pattern → False."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=["/work/**"], exclude=[])
        assert is_in_scope("/personal/project", cfg) is False

    def test_is_in_scope_multiple_includes_none_match(self):
        """None of multiple include patterns match → False."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=["/work/**", "/oss/**"], exclude=[])
        assert is_in_scope("/personal/hobby", cfg) is False

    def test_is_in_scope_one_of_multiple_includes_matches(self):
        """At least one include pattern matches → True."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=["/work/**", "/oss/**"], exclude=[])
        assert is_in_scope("/oss/myproject", cfg) is True


# ---------------------------------------------------------------------------
# AC-3 — exclude match
# ---------------------------------------------------------------------------

class TestIsInScopeExcludeMatch:
    """Matching an exclude pattern → out of scope regardless of include."""

    def test_is_in_scope_exclude_match_returns_false(self):
        """cwd matching exclude pattern → False even with no include rules."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=[], exclude=["/secret/**"])
        assert is_in_scope("/secret/project", cfg) is False

    def test_is_in_scope_exclude_wins_over_include(self):
        """Exclude beats include when both match → False."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=["/work/**"], exclude=["/work/secret/**"])
        assert is_in_scope("/work/secret/stuff", cfg) is False

    def test_is_in_scope_exclude_does_not_affect_non_matching(self):
        """Exclude pattern present but path doesn't match it → True."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=[], exclude=["/secret/**"])
        assert is_in_scope("/public/project", cfg) is True


# ---------------------------------------------------------------------------
# Glob semantics — ** vs * vs ?
# ---------------------------------------------------------------------------

class TestIsInScopeGlobSemantics:
    """Verify correct glob semantics for **, *, and ?."""

    def test_is_in_scope_star_star_matches_deep_path(self):
        """** matches any number of path segments."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=["/a/**"], exclude=[])
        assert is_in_scope("/a/b/c/d", cfg) is True

    def test_is_in_scope_star_star_matches_direct_child(self):
        """** also matches a single path segment."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=["/a/**"], exclude=[])
        assert is_in_scope("/a/b", cfg) is True

    def test_is_in_scope_single_star_does_not_cross_segments(self):
        """* matches within a single path segment only."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=["/a/*"], exclude=[])
        # /a/b/c has two levels below /a, * should NOT match
        assert is_in_scope("/a/b/c", cfg) is False

    def test_is_in_scope_single_star_matches_same_level(self):
        """* matches exactly one path segment."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=["/a/*"], exclude=[])
        assert is_in_scope("/a/b", cfg) is True

    def test_is_in_scope_question_mark_matches_single_char(self):
        """? matches exactly one non-separator character."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=["/a/?"], exclude=[])
        assert is_in_scope("/a/x", cfg) is True

    def test_is_in_scope_question_mark_does_not_match_two_chars(self):
        """? does not match two characters."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=["/a/?"], exclude=[])
        assert is_in_scope("/a/xx", cfg) is False

    def test_is_in_scope_question_mark_does_not_cross_segments(self):
        """? does not match a path separator."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=["/a/?"], exclude=[])
        assert is_in_scope("/a/b/c", cfg) is False


# ---------------------------------------------------------------------------
# Glob — regex metachars in patterns treated as literals
# ---------------------------------------------------------------------------

class TestIsInScopeGlobEscapesRegexMetachars:
    """Literal dots and other regex metacharacters in patterns are not regex-expanded."""

    def test_glob_escapes_regex_metachars_dot_literal(self):
        """Pattern /a.b.c treats dots as literal, not regex wildcards."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=["/a.b.c"], exclude=[])
        # Literal match succeeds
        assert is_in_scope("/a.b.c", cfg) is True
        # Regex-style wildcard should NOT match
        assert is_in_scope("/aXbXc", cfg) is False

    def test_glob_escapes_regex_metachars_plus(self):
        """Pattern with + in path name treats it as literal."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=["/a+b/**"], exclude=[])
        assert is_in_scope("/a+b/project", cfg) is True
        assert is_in_scope("/ab/project", cfg) is False

    def test_glob_escapes_regex_metachars_parens(self):
        """Pattern with parentheses treats them as literals."""
        from ephemeris.scope import ScopeConfig, is_in_scope

        cfg = ScopeConfig(include=["/my(project)/**"], exclude=[])
        assert is_in_scope("/my(project)/src", cfg) is True
        assert is_in_scope("/myproject/src", cfg) is False
