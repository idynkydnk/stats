import ast
import unittest
from pathlib import Path

from flask import Flask, jsonify, request


class ErrorPageTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(Path('templates').resolve()))
        tree = ast.parse(Path('stats.py').read_text())
        selected = [node for node in tree.body if
                    isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_ERROR_PAGE_COPY' for t in node.targets)
                    or isinstance(node, ast.FunctionDef) and node.name in {'_wants_json_error_response', '_render_error_page'}]
        self.namespace = dict(app=self.app, jsonify=jsonify, request=request)
        exec(compile(ast.Module(body=selected, type_ignores=[]), 'stats.py', 'exec'), self.namespace)

    def test_error_page_survives_failed_database_context(self):
        @self.app.context_processor
        def failed_navigation():
            raise RuntimeError('database unavailable')
        with self.app.test_request_context('/broken'):
            html, status = self.namespace['_render_error_page'](None, 500)
        self.assertEqual(status, 500)
        self.assertIn('Try again', html)
        self.assertIn('Taking a quick timeout', html)
        self.assertNotIn('cdnjs', html)

    def test_api_errors_remain_json(self):
        with self.app.test_request_context('/api/broken'):
            response, status = self.namespace['_render_error_page'](None, 503)
        self.assertEqual(status, 503)
        self.assertFalse(response.json['success'])
        self.assertEqual(response.json['code'], 503)

    def test_missing_page_offers_safe_home_link(self):
        with self.app.test_request_context('/missing'):
            html, status = self.namespace['_render_error_page'](None, 404)
        self.assertEqual(status, 404)
        self.assertIn('href="/"', html)
        self.assertNotIn('window.location.replace', html)


if __name__ == '__main__':
    unittest.main()
