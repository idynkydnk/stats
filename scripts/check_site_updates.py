#!/usr/bin/env python3
"""Require an explicit announcement decision for every newly pushed commit."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from site_update_notes import parse_site_update_note


def check(before, after):
    reviewed = json.loads((ROOT / 'data/site_update_copy.json').read_text())
    # New branches have no before commit. Check their tip, not all old history.
    revisions = [f'{before}..{after}'] if before.strip('0') else ['-1', after]
    commits = subprocess.check_output(
        ['git', 'rev-list', '--no-merges', *revisions], cwd=ROOT, text=True,
    ).splitlines()
    missing = []
    for sha in commits:
        if sha in reviewed:
            continue
        body = subprocess.check_output(
            ['git', 'show', '-s', '--format=%b', sha], cwd=ROOT, text=True,
        )
        try:
            note = parse_site_update_note(body)
        except ValueError:
            note = None
        if note is None:
            missing.append(sha[:7])
    if missing:
        print('Missing site update decision: ' + ', '.join(missing))
        print('Add a Site-Update: title paragraph to each commit body, or '
              'Site-Update: none for changes with nothing to announce. '
              'See docs/site-updates.md.')
        return 1
    print('Every pushed change has a site update or an explicit skip.')
    return 0


if __name__ == '__main__':
    sys.exit(check(sys.argv[1], sys.argv[2]))
