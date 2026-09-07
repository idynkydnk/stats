"""Explicit, reader-facing notes carried in commit messages."""
import re


def parse_site_update_note(body):
    """Return a published note, False for an explicit skip, or None if missing.

    The note is one paragraph, separated from technical commit details by a
    blank line. Its first line supplies the title; subsequent lines supply copy.
    """
    match = re.search(r'^Site-Update:[ \t]*(.*)$', body or '', re.MULTILINE)
    if not match:
        return None
    title = match.group(1).strip()
    if title.lower() == 'none':
        return False
    if not title:
        raise ValueError('Site-Update needs a readable title or "none".')
    lines = []
    for line in body[match.end():].removeprefix('\r').removeprefix('\n').splitlines():
        if not line.strip() or re.match(r'^[A-Za-z-]+:', line):
            break
        lines.append(line.strip())
    return {'subject': title, 'body': ' '.join(lines)}
