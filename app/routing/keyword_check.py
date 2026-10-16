"""
app/routing/keyword_check.py
============================
Stage 2: Heuristic keyword inspection guard (~40 high-precision terms).
Matches user prompt against code debugging, syntax, action verb, and tooling terms.
Uses word-boundary regex matching to prevent false positives (e.g. 'repo' in 'report').
Recognizes conceptual inquiry intent vs code generation intent.
"""

import re

from app.routing.schemas import RouteDecision

CODING_KEYWORDS = [
    # Error/debugging signals
    "debug",
    "traceback",
    "stack trace",
    "stacktrace",
    "exception",
    "error message",
    "compile error",
    "syntax error",
    "null pointer",
    "segfault",
    "crash",
    # Code action verbs
    "refactor",
    "optimize this function",
    "fix this code",
    "write a script",
    "write a function",
    "implement",
    "unit test",
    "test case",
    # Code structure/syntax literals
    "def ",
    "class ",
    "import ",
    "function(",
    "return ",
    "```",
    "console.log",
    "print(",
    "for loop",
    "while loop",
    # File/repo/dev-tooling terms
    "repo",
    "repository",
    "pull request",
    "commit",
    "merge conflict",
    "dependency",
    "package.json",
    "requirements.txt",
    "dockerfile",
    "api endpoint",
    "database query",
    "sql query",
    "regex",
    # Language names
    "python",
    "javascript",
    "java",
    "typescript",
    "sql",
    "bash script",
    "shell script",
]

LANGUAGE_NAMES = {"python", "javascript", "java", "typescript", "sql", "bash script", "shell script"}
CONCEPTUAL_WORDS = {
    "what",
    "why",
    "how",
    "explain",
    "compare",
    "list",
    "describe",
    "summarize",
    "advantage",
    "advantages",
    "disadvantage",
    "disadvantages",
}
ACTION_VERBS = {
    "write",
    "script",
    "code",
    "fix",
    "debug",
    "run",
    "execute",
    "create",
    "implement",
    "build",
    "refactor",
    "test",
    "optimize",
    "def",
    "class",
    "import",
}


def check_keywords(prompt: str) -> RouteDecision | None:
    """Stage 2 Waterfall check.

    Checks prompt for strong coding-intent keyword signals using word boundary precision.
    """
    if not prompt or not prompt.strip():
        return None

    prompt_lower = prompt.lower()
    is_conceptual = any(word in prompt_lower for word in CONCEPTUAL_WORDS)
    has_action = any(verb in prompt_lower for verb in ACTION_VERBS)

    for kw in CODING_KEYWORDS:
        # If it's just a language name mentioned conceptually without an action verb, do not force coding
        if kw in LANGUAGE_NAMES and is_conceptual and not has_action:
            continue

        # Check literal match if contains punctuation/spaces (e.g. "def ", "```", "function(")
        if any(char in kw for char in [" ", "(", "`", "."]):
            if kw in prompt_lower:
                return RouteDecision(
                    role="coding",
                    confidence=0.85,
                    method="keyword",
                    reasoning=f"Matched coding keyword pattern '{kw}'.",
                )
        else:
            # Word boundary regex match for single words (e.g. "repo", "crash", "python")
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, prompt_lower):
                return RouteDecision(
                    role="coding",
                    confidence=0.85,
                    method="keyword",
                    reasoning=f"Matched coding keyword term '{kw}'.",
                )

    return None
