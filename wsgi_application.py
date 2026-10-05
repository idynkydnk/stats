"""Keep a readable outage response available when Flask cannot start."""
import importlib
import json
import logging
from pathlib import Path


def load_application():
    try:
        return importlib.import_module('stats').app
    except Exception:
        logging.exception('Stats failed to start; serving the outage page')
        return unavailable_application


def unavailable_application(environ, start_response):
    message = 'Stats is temporarily unavailable. Give it a moment, then try again. If you were saving a game, check your games before adding it again.'
    if environ.get('PATH_INFO', '').startswith('/api'):
        body = json.dumps(dict(success=False, error='Stats is temporarily unavailable',
                               message=message, code=503)).encode('utf-8')
        content_type = 'application/json'
    else:
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape
            templates = Environment(loader=FileSystemLoader(Path(__file__).parent / 'templates'),
                                    autoescape=select_autoescape(['html']))
            html = templates.get_template('error.html').render(
                error_code=503, error_title='Taking a quick timeout',
                error_call='Temporarily unavailable', error_message=message)
        except Exception:
            # Even a missing template or dependency must leave a valid response.
            html = '<!doctype html><html lang="en"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Stats is temporarily unavailable</title><body><h1>Taking a quick timeout</h1><p>' + message + '</p><a href="/">Try again</a></body></html>'
        body = html.encode('utf-8')
        content_type = 'text/html'
    start_response('503 Service Unavailable', [
        ('Content-Type', content_type + '; charset=utf-8'),
        ('Content-Length', str(len(body))), ('Retry-After', '60'),
        ('Cache-Control', 'no-store'),
    ])
    return [] if environ.get('REQUEST_METHOD') == 'HEAD' else [body]
