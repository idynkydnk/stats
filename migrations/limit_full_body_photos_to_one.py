#!/usr/bin/env python3
"""Keep one full-body photo per player; delete extras. Safe to re-run."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from player_functions import trim_all_players_full_body_photos  # noqa: E402


if __name__ == '__main__':
    removed = trim_all_players_full_body_photos()
    print(f'Removed {removed} extra full-body photo(s).')
