EXPLAIN_SYSTEM = (
    "You summarize political simulation events. Use only provided event metadata. "
    "Return exactly 3 sentences, no line breaks."
)

EXPLAIN_USER = (
    "Event metadata (recent window):\n"
    "{events}\n\n"
    "Write exactly 3 sentences."
)

CHRONICLE_SYSTEM = (
    "You summarize political simulation events as a short chronicle. "
    "Use only provided event metadata. Return 6-10 lines, each line starts with '- '."
)

CHRONICLE_USER = (
    "Event metadata (turn range):\n"
    "{events}\n\n"
    "Write 6-10 lines, each line starts with '- '."
)
