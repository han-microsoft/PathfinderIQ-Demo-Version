"""ReflectionController (K10) — bounded post-run self-assessment loop.

Domain-blind: a deterministic loop controller over a single request's original
message. Was ``agent/reflection.py`` (promoted from ``control_mechanisms/`` by
R4 of the agent_runtime inquisitor audit).
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_YES_PATTERN = re.compile(r"^\s*yes\b", re.IGNORECASE)


class ReflectionController:
    """Deterministic reflection loop controller for a single request."""

    def __init__(self, original_message: str, max_rounds: int = 2) -> None:
        self.original_message = original_message
        self.max_rounds = max(1, max_rounds)
        self.round = 0
        self._done = False

    @property
    def is_done(self) -> bool:
        return self._done or self.round >= self.max_rounds

    def should_reflect(self) -> bool:
        """Return True when another assessment pass is allowed."""
        return not self.is_done

    def get_assessment_prompt(self) -> str:
        """Return the system-authored assessment request for the next pass."""
        return (
            f"SYSTEM REFLECTION CHECK (round {self.round + 1}/{self.max_rounds})\n\n"
            f"The operator's original request was:\n"
            f'"{self.original_message}"\n\n'
            "Assess: has the investigation been adequately addressed?\n"
            "Consider:\n"
            "- Are priority actions populated with evidence, not just data gaps?\n"
            "- Are there critical gaps that justify another investigation round?\n"
            "- Have the summary panels been updated with the confirmed state?\n\n"
            "Answer YES on the first line if done, or NO followed by what remains missing."
        )

    def parse_response(self, response_text: str) -> bool:
        """Record the assessment result. Returns True when the run is done."""
        self.round += 1
        first_line = response_text.strip().split("\n", 1)[0] if response_text.strip() else ""
        if _YES_PATTERN.match(first_line):
            self._done = True
            logger.info("reflection.done: round=%d verdict=YES", self.round)
            return True

        logger.info("reflection.continue: round=%d verdict=%s", self.round, first_line[:200])
        return False
