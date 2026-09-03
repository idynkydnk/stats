"""Shared player-name identity rules.

Names are user-entered labels, but leading and trailing whitespace is never
part of a person's identity.  Keeping this rule in one small module lets the
database writers and readers agree on the same canonical value.
"""

import unicodedata


def canonical_player_name(value):
    """Return the stored/display form of a player name."""
    if not isinstance(value, str):
        return value
    return value.strip()


def player_name_identity_key(value):
    """Return a comparison key for names that render as the same person."""
    name = canonical_player_name(value)
    if not isinstance(name, str):
        return name
    # Historical imports can differ by Unicode form, invisible whitespace, or
    # capitalization even though the autocomplete renders the same label.
    normalized = unicodedata.normalize('NFKC', name)
    return ' '.join(normalized.split()).casefold()


def unique_player_names(values):
    """Canonicalize and de-duplicate names while preserving first-seen order."""
    names = []
    seen = set()
    for value in values:
        name = canonical_player_name(value)
        key = player_name_identity_key(name)
        if not name or key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names
