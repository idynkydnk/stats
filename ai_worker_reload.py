"""Restart an idle AI worker when deployed Python source files change."""
from pathlib import Path


def source_version(root):
    """Include source additions/removals as well as edits without importing them."""
    return tuple(
        (path.name, path.stat().st_mtime_ns, path.stat().st_size)
        for path in sorted(Path(root).glob('*.py'))
    )


def restart_if_source_changed(root, loaded_version, restart, log):
    if source_version(root) == loaded_version:
        return False
    log('Application code changed; restarting before claiming another AI job.')
    restart()
    return True
