"""Turn exceptions into something a user can act on.

Raw exception text was being streamed straight into the chat bubble, so a user
(or a hackathon judge) would read things like:

    run_keyword_strategy() got an unexpected keyword argument 'angle'
    Request timed out.

That tells them nothing about what to do next, and it looks broken even when
the run is recoverable. The full text is still recorded on the run for
debugging; only the chat gets the readable version.
"""
from __future__ import annotations

import re

# (matcher, what the user is told, whether the work can be resumed)
_RULES: list[tuple[re.Pattern, str, bool]] = [
    (
        re.compile(r"budget|call cap|DFSBudgetExceeded", re.I),
        "I've used up this run's DataForSEO budget, so I stopped before "
        "spending more. Tell me to continue and I'll extend it, or ask me to "
        "work with what we already have.",
        True,
    ),
    (
        re.compile(r"confirm_market|no market confirmed", re.I),
        "I still need the target market before I can research anything: which "
        "country your audience searches from, and in which language.",
        True,
    ),
    (
        re.compile(r"timed out|timeout|ReadTimeout|APITimeout", re.I),
        "That step took longer than its time limit and I stopped it rather "
        "than leave it hanging. Ask me to retry — the work already done is "
        "kept, so it picks up from there.",
        True,
    ),
    (
        re.compile(r"rate.?limit|429|too many requests", re.I),
        "The model provider is rate-limiting us right now. Give it a moment "
        "and ask me to retry.",
        True,
    ),
    (
        re.compile(r"401|403|unauthorized|forbidden|invalid.*(api key|credential)", re.I),
        "A service rejected our credentials, so I couldn't complete that step. "
        "This needs an API key checked before retrying.",
        False,
    ),
    (
        re.compile(r"unexpected keyword argument|takes \d+ positional|TypeError", re.I),
        "I called one of my own tools incorrectly and stopped rather than "
        "guess. Ask me to try again and I'll use the correct form.",
        True,
    ),
    (
        re.compile(r"JSON|parse|decode", re.I),
        "I couldn't read a response from one of the services. Ask me to retry "
        "that step.",
        True,
    ),
    (
        re.compile(r"connection|network|DNS|unreachable|ConnectError", re.I),
        "I couldn't reach an external service. That's usually temporary — ask "
        "me to retry.",
        True,
    ),
]

_FALLBACK = (
    "Something went wrong on that step and I stopped rather than carry on with "
    "half an answer. The details are recorded on the run if you want to look, "
    "and you can ask me to retry."
)


def user_message(exc: BaseException | str) -> str:
    """A readable, actionable sentence for the chat."""
    raw = str(exc).strip()
    if not raw:
        return _FALLBACK
    for pattern, message, _ in _RULES:
        if pattern.search(raw):
            return message
    return _FALLBACK


def is_recoverable(exc: BaseException | str) -> bool:
    """Whether retrying is worth suggesting."""
    raw = str(exc).strip()
    for pattern, _, recoverable in _RULES:
        if pattern.search(raw):
            return recoverable
    return True


def detail(exc: BaseException | str, limit: int = 500) -> str:
    """The raw text, for the run record and the logs — never for the chat."""
    return f"{type(exc).__name__}: {exc}"[:limit] if isinstance(exc, BaseException) else str(exc)[:limit]
