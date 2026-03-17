"""ask_work_iq — spoofed Microsoft 365 data query tool.

Module role:
    Simulates the Work IQ MCP server's ``ask_work_iq`` tool. Takes a
    natural language question, matches it against a curated catalog of
    scenario-relevant M365 responses using keyword overlap scoring, and
    returns the best match. Falls back to a generic "no results" response
    when no catalog entry scores above threshold.

    The catalog entries are written to complement the telecom fibre-cut
    scenario: emails from NOC staff about the SYD-MEL corridor, calendar
    entries for infrastructure reviews, Teams messages from the NOC
    channel, and document references for fibre route plans.

Design rationale:
    The real Work IQ exposes a single ``ask_work_iq(question) → text``
    tool. This spoof preserves that exact interface so the agent's
    prompt instructions and tool-calling behaviour are identical whether
    running against the spoof or a live MCP server. Keyword matching is
    deliberately simple — the LLM's question reformulation provides
    sufficient signal for demo-quality retrieval.

Key collaborators:
    - ``agent_framework.tool``      — ``@tool`` decorator for JSON schema
    - ``app.observability``         — ``traced_tool`` OTel wrapper
    - ``_responses.py``             — catalog definition (imported lazily)

Dependents:
    Imported by: ``tools/workiq/__init__.py``
"""

from __future__ import annotations

import json
import logging
import re
from typing import Annotated

from agent_framework import tool
from pydantic import Field

from app.observability import traced_tool

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> set[str]:
    """Extract lowercase alphanumeric tokens from text.

    Splits on non-word characters and filters tokens shorter than 2 chars
    to reduce noise from articles and prepositions.

    Args:
        text: Raw input string.

    Returns:
        Set of lowercase tokens (length >= 2).
    """
    return {t.lower() for t in re.split(r"\W+", text) if len(t) >= 2}


def _score_match(question_tokens: set[str], entry_tokens: set[str]) -> float:
    """Compute normalised keyword overlap between question and catalog entry.

    Uses Jaccard-like scoring: intersection size divided by the smaller set
    size. This favours short, focused questions matching long catalog
    keyword lists without penalising keyword-rich entries.

    Args:
        question_tokens: Tokens from the user's question.
        entry_tokens: Tokens from a catalog entry's keyword set.

    Returns:
        Score in [0.0, 1.0]. Higher = better match.
    """
    if not question_tokens or not entry_tokens:
        return 0.0
    overlap = question_tokens & entry_tokens
    # Normalise by the smaller set to avoid penalising
    # short questions against keyword-rich catalog entries
    return len(overlap) / min(len(question_tokens), len(entry_tokens))


# ── Minimum score threshold for a catalog match ─────────────────────────
# Below this, the tool returns the "no results" fallback. Set low because
# the LLM's question reformulation may only share 1-2 keywords with the
# catalog entry, and that's still a valid match for demo purposes.
_MATCH_THRESHOLD = 0.15


@tool
@traced_tool("ask_work_iq", backend="spoof")
async def ask_work_iq(
    question: Annotated[str, Field(
        description=(
            "A natural language question about the user's Microsoft 365 data. "
            "Examples: 'Any emails about the SYD-MEL fibre corridor?', "
            "'What meetings are scheduled about infrastructure resilience?', "
            "'Teams messages from the NOC channel about outages today?'"
        ),
    )],
) -> str:
    """Query Microsoft 365 data (emails, calendar, Teams, documents, people).

    Searches the user's M365 data for information relevant to the question.
    Returns a natural-language summary of matching items including source
    type (email, meeting, Teams message, document), sender/author, date,
    and key content excerpts.

    Args:
        question: Natural language question about M365 data.

    Returns:
        JSON string with status, source type, and response text.

    Side effects:
        Logs the query and matched catalog entry for observability.
    """
    # Lazy import to keep module load fast and avoid circular deps
    from tools.workiq._responses import RESPONSE_CATALOG

    question_tokens = _tokenize(question)

    # Score every catalog entry against the question
    best_score = 0.0
    best_entry = None
    for entry in RESPONSE_CATALOG:
        entry_tokens = _tokenize(entry["keywords"])
        score = _score_match(question_tokens, entry_tokens)
        if score > best_score:
            best_score = score
            best_entry = entry

    if best_entry and best_score >= _MATCH_THRESHOLD:
        logger.info(
            "tool.ask_work_iq.matched",
            extra={
                "question": question[:200],
                "matched_id": best_entry["id"],
                "score": round(best_score, 3),
                "source_type": best_entry["source_type"],
            },
        )
        return json.dumps({
            "status": "ok",
            "source_type": best_entry["source_type"],
            "match_confidence": round(best_score, 3),
            "response": best_entry["response"],
        })

    # No match above threshold — return a realistic "nothing found" response
    logger.info(
        "tool.ask_work_iq.no_match",
        extra={"question": question[:200], "best_score": round(best_score, 3)},
    )
    return json.dumps({
        "status": "no_results",
        "source_type": "none",
        "match_confidence": 0.0,
        "response": (
            "I searched your emails, calendar, Teams messages, and documents "
            "but didn't find anything directly relevant to that question. "
            "Try rephrasing with specific names, dates, or project references."
        ),
    })
