"""Canonical category labels shared by website and app game writes."""


def canonical_other_category(value):
    aliases = {
        'card game': 'Card games',
        'card games': 'Card games',
        'board game': 'Board games',
        'board games': 'Board games',
    }
    if not isinstance(value, str):
        return value
    return aliases.get(value.strip().casefold(), value)
