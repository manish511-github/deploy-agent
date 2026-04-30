"""Permission ruleset evaluator.

Ported from OpenCode's permission/evaluate.ts.
Rules are (permission, pattern, action) tuples evaluated last-match-wins.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Literal


Action = Literal["allow", "deny", "ask"]


@dataclass(frozen=True, slots=True)
class Rule:
    """A single permission rule.

    Examples:
        Rule("exec_script", "rm -rf /*", "deny")
        Rule("send_agent_task", "device.restart", "ask")
        Rule("*", "*", "allow")
    """

    permission: str
    pattern: str
    action: Action


Ruleset = list[Rule]


def wildcard_match(value: str, pattern: str) -> bool:
    """Match a value against a glob pattern.

    Uses fnmatch (stdlib) so patterns like ``"*"``, ``"rm -rf *"``,
    ``"device.*"`` all work as expected.
    """
    return fnmatch.fnmatch(value, pattern)


def evaluate(permission: str, pattern: str, *rulesets: Ruleset) -> Rule:
    """Evaluate permission + pattern against merged rulesets.

    Last-match-wins: we iterate all rules in order (flattening all
    rulesets) and the final matching rule determines the action.

    If nothing matches, returns a fail-closed deny rule.

    Args:
        permission: The permission being checked, e.g. ``"exec_script"``.
        pattern: The concrete pattern, e.g. ``"apt install nginx"``.
        *rulesets: One or more rulesets merged in order.
                   Later rulesets override earlier ones.

    Returns:
        The matching ``Rule`` (or a default deny rule).
    """
    matched: Rule | None = None
    for rule in (r for rs in rulesets for r in rs):
        if wildcard_match(permission, rule.permission) and wildcard_match(pattern, rule.pattern):
            matched = rule
    return matched if matched is not None else Rule(permission="*", pattern="*", action="deny")


def ruleset_from_dict(raw: dict[str, str | dict[str, str]]) -> Ruleset:
    """Build a Ruleset from a nested dict config.

    Input shape mirrors OpenCode's config format::

        {
            "exec_script": "allow",
            "send_agent_task": {
                "device.restart": "ask",
                "*": "allow",
            },
            "fleet_target": {
                "count<=3": "allow",
                "count<=20": "ask",
                "*": "deny",
            },
        }

    A string value is shorthand for ``{"*": <action>}``.
    """
    rules: Ruleset = []
    for perm, val in raw.items():
        if isinstance(val, str):
            rules.append(Rule(permission=perm, pattern="*", action=val))
        else:
            for pat, act in val.items():
                rules.append(Rule(permission=perm, pattern=pat, action=act))
    return rules
