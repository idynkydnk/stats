from pathlib import Path
import json
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit, parse_qs

from flask import Flask, url_for
from template_delivery import player_stats_url, register_template_delivery


class TemplateDeliveryTests(unittest.TestCase):
    def test_compiled_templates_reused_between_workers_and_source_changes_invalidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'example.html').write_text('Hello {{ name }}')
            def worker():
                app = Flask(__name__, template_folder=str(root))
                app.extensions['stats_response_cache'] = SimpleNamespace(directory=root / 'cache')
                return app
            first = worker()
            register_template_delivery(first)
            second = worker()
            with patch.object(second.jinja_env, 'compile', wraps=second.jinja_env.compile) as compile_template:
                register_template_delivery(second)
                self.assertEqual(compile_template.call_count, 0)
                self.assertEqual(second.jinja_env.get_template('example.html').render(name='second'), 'Hello second')
            (root / 'example.html').write_text('Changed {{ name }}')
            third = worker()
            register_template_delivery(third)
            self.assertEqual(third.jinja_env.get_template('example.html').render(name='third'), 'Changed third')
            self.assertEqual((root / 'cache/templates').stat().st_mode & 0o777, 0o700)
            for file in (root / 'cache/templates').iterdir():
                self.assertEqual(file.stat().st_mode & 0o777, 0o600)

    def test_bulk_player_links_preserve_prefix_filters_unicode_and_escape_boundaries(self):
        app = Flask(__name__)
        app.add_url_rule('/player/<year>/<name>/', endpoint='player_stats')
        @app.url_defaults
        def defaults(endpoint, values):
            values.update(view='shared-view', location='A & B', division='women')
        with app.test_request_context('/stats', environ_overrides={'SCRIPT_NAME': '/prefix'}):
            with patch('template_delivery.url_for', wraps=url_for) as build:
                for name in ['Alice', 'Zoë & 李', "A?B#C% / D", '</a><script>alert(1)</script>']:
                    actual = urlsplit(player_stats_url('All years', name))
                    expected = urlsplit(url_for('player_stats', year='All years', name=name))
                    self.assertEqual(unquote(actual.path), unquote(expected.path))
                    self.assertEqual(parse_qs(actual.query), parse_qs(expected.query))
                    self.assertEqual(actual.fragment, '')
                self.assertEqual(build.call_count, 1)
        with app.test_request_context('/stats'):
            self.assertTrue(player_stats_url('2026', 'Alice').startswith('/player/2026/'))

    def test_compact_standings_keep_every_value_python_rounding_and_safe_names(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Flask(__name__, template_folder=directory)
            app.extensions['stats_response_cache'] = SimpleNamespace(directory=directory)
            register_template_delivery(app)
            rows = [['</script><img onerror=bad>', 1, 7, .125, 12.345]]
            rendered = app.jinja_env.from_string('{{ rows|standings_records|tojson }}').render(rows=rows)
            self.assertNotIn('</script>', rendered)
            self.assertEqual(json.loads(rendered), [rows[0] + [format(12.345, '.2f'), '12']])
