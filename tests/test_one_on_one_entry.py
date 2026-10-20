"""Exercise the rendered 1v1 field, its choices, and its save destination."""
from html.parser import HTMLParser
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from flask import render_template
from jinja2 import ChoiceLoader, DictLoader

from one_on_one import FORMATS
from tests import test_saved_game_popup as saved_game_tests


class EntryForm(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.inputs, self.forms, self.choices = [], {}, {}
        self.list_id = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input':
            self.inputs.append(attrs)
        elif tag == 'form':
            self.forms[attrs['id']] = attrs['action']
        elif tag == 'datalist':
            self.list_id = attrs['id']
            self.choices[self.list_id] = []
        elif tag == 'option' and self.list_id:
            self.choices[self.list_id].append(attrs['value'])

    def handle_endtag(self, tag):
        if tag == 'datalist':
            self.list_id = None


class OneOnOneEntryTests(unittest.TestCase):
    def setUp(self):
        saved_game_tests.SavedGamePopupTests.setUp(self)
        self.app.jinja_loader = ChoiceLoader([DictLoader({
            'entry_base': '{% block extra_css %}{% endblock %}{% block content %}{% endblock %}{% block extra_js %}{% endblock %}',
            'partials/page_header_actions.html': '',
        }), self.app.jinja_loader])
        for endpoint in ('stats', 'vollis_stats', 'other_stats'):
            self.app.add_url_rule('/' + endpoint, endpoint, lambda: '')
        self.render.side_effect = lambda template, **values: render_template(
            template, base_template='entry_base', one_on_one_formats=FORMATS,
            locations=[], last_location='', inline_stats_script='', **values)
        catalog = dict(names=list(FORMATS) + [' italian SHORT court ', 'No jump', 'Vollis kings', 'Sequence'],
                       types=['Volleyball', 'Cards'], defaults={}, requiring_scores=[])
        patcher = patch('other_functions.other_game_entry_catalog', return_value=catalog)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_other_suggestions_exclude_singles_but_keep_other_volleyball(self):
        response = self.client.get('/add_other_game/')
        self.assertEqual(response.status_code, 200)
        form = EntryForm(response.get_data(as_text=True))
        self.assertEqual(form.choices['game_names'], ['No jump', 'Vollis kings', 'Sequence'])
        field = next(f for f in form.inputs if f.get('name') == 'game_name')
        self.assertEqual(field['placeholder'], 'Game Name')
        self.assertEqual(form.forms['add-other-form'], '/add_other_game/')

    def test_both_singles_pages_have_one_searchable_format_field(self):
        for path, selected in (
            ('/add_vollis_game/', 'Vollis'),
            ('/add_other_game/?one_on_one=1&format=Italian+short+court', 'Italian short court'),
            ('/add_other_game/?one_on_one=1', ''),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                form = EntryForm(html)
                fields = [f for f in form.inputs if f.get('name') == 'game_name']
                self.assertEqual(len(fields), 1)
                self.assertEqual(fields[0]['type'], 'text')
                self.assertEqual(fields[0]['placeholder'], 'Volleyball Format')
                self.assertEqual(fields[0]['value'], selected)
                self.assertNotIn('one-on-one-entry', html)
                self.assertNotIn('#game_name-wrap,', html)
                if 'add-other-form' in form.forms:
                    self.assertEqual(form.choices['game_names'], list(FORMATS))
                    action = urlsplit(form.forms['add-other-form'])
                    self.assertEqual(parse_qs(action.query), {'one_on_one': ['1']})
                    category = next(f for f in form.inputs if f.get('name') == 'game_type')
                    self.assertEqual(category['value'], 'Volleyball')

    def test_rendered_action_saves_singles_and_returns_to_selected_format(self):
        html = self.client.get('/add_other_game/?one_on_one=1&format=Italian+short+court').get_data(as_text=True)
        action = EntryForm(html).forms['add-other-form']
        fields = dict(self.fields, game_name='  italian SHORT court ', game_type='Volleyball',
                      winner2='', loser2='')
        response = self.client.post(action, data=fields)
        self.write.assert_called_once()
        self.assertEqual(self.write.call_args.args[2], 'Italian short court')
        self.assertEqual(self.write.call_args.args[3], ['Alice'])
        self.assertEqual(self.write.call_args.args[5], ['Chris'])
        self.assertEqual(parse_qs(urlsplit(response.location).query),
                         {'one_on_one': ['1'], 'format': ['Italian short court']})
        html = self.client.get(response.location).get_data(as_text=True)
        self.assertIn('id="saved-game-popup"', html)
        self.assertIn('value="Italian short court"', html)

    def test_singles_save_rejects_non_singles_results(self):
        valid = dict(self.fields, game_name='Italian short court', game_type='Volleyball',
                     winner2='', loser2='')
        for changes in ({'winner2': 'Bob'}, {'loser1': 'Alice'},
                        {'game_name': '   '}, {'game_type': 'Cards'}):
            with self.subTest(changes=changes):
                self.client.post('/add_other_game/?one_on_one=1', data=dict(valid, **changes))
        self.write.assert_not_called()

    def test_new_format_is_saved_as_one_on_one(self):
        fields = dict(self.fields, game_name='  Back line lefty  ', game_type='Volleyball',
                      winner2='', loser2='')
        response = self.client.post('/add_other_game/?one_on_one=1', data=fields)
        self.write.assert_called_once()
        self.assertEqual(self.write.call_args.args[2], 'Back line lefty')
        self.assertTrue(self.write.call_args.kwargs['one_on_one'])
        self.assertEqual(parse_qs(urlsplit(response.location).query)['format'], ['Back line lefty'])


if __name__ == '__main__':
    unittest.main()
