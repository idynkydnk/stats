import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from ai_worker_reload import source_version, restart_if_source_changed


class AIWorkerReloadTests(unittest.TestCase):
    def test_prompt_change_restarts_worker_before_more_jobs(self):
        with tempfile.TemporaryDirectory() as root:
            prompt = Path(root) / 'email_content.py'
            prompt.write_text('old factual prompt')
            loaded = source_version(root)
            restart, log = Mock(), Mock()
            self.assertFalse(restart_if_source_changed(root, loaded, restart, log))
            restart.assert_not_called()
            prompt.write_text('new funny prompt using comments and traits')
            self.assertTrue(restart_if_source_changed(root, loaded, restart, log))
            restart.assert_called_once_with()
            log.assert_called_once()
            self.assertFalse(restart_if_source_changed(root, source_version(root), restart, log))

    def test_job_database_and_images_do_not_trigger_restart(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / 'stats.py').write_text('app code')
            loaded = source_version(root)
            (Path(root) / 'stats.db').write_text('a completed job')
            (Path(root) / 'hero.png').write_bytes(b'image')
            self.assertEqual(source_version(root), loaded)
            (Path(root) / 'new_module.py').write_text('new code')
            self.assertNotEqual(source_version(root), loaded)


if __name__ == '__main__':
    unittest.main()
