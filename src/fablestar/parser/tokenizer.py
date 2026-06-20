"""Input tokenizer — splits raw player input into a lowercase token list via shlex."""

import shlex


def tokenize(input_string: str) -> list[str]:
    """
    Split input string into tokens.
    Supports quoted strings for multi-word arguments (e.g. 'say "hello world"').
    """
    if not input_string:
        return []

    try:
        # shlex handles quotes properly
        return shlex.split(input_string.lower())
    except ValueError:
        # Fallback for malformed quotes
        return input_string.lower().split()
