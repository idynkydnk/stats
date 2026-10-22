"""Public support/privacy pages and browser controls for the app's safety APIs."""
import os
from urllib.parse import urlsplit

from flask import abort, make_response, request, session


def safe_return_path(value):
    value = str(value or '/')
    try:
        parsed = urlsplit(value)
    except ValueError:
        return '/'
    if (not value.startswith('/') or value.startswith('//') or parsed.scheme or
            parsed.netloc or '\\' in value or any(ord(c) < 32 for c in value)):
        return '/'
    return value


def register_policy_pages(app, service):
    def page(template, **context):
        # These essential pages remain available when stats/navigation queries fail.
        response = make_response(app.jinja_env.get_template(template).render(
            support_email=os.environ.get('STATS_SUPPORT_EMAIL', 'idynkydnk@gmail.com'),
            signed_in=bool(session.get('logged_in')),
            **context,
        ))
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        return response

    @app.get('/privacy')
    def privacy_policy():
        return page('privacy_policy.html')

    @app.get('/support')
    def support_page():
        return page('support_page.html')

    @app.get('/community-guidelines')
    def community_guidelines():
        return page('community_guidelines.html')

    @app.get('/privacy-settings')
    @service.login_required
    def privacy_settings():
        return page('privacy_settings.html', return_path=safe_return_path(request.args.get('next')))

    @app.get('/report-content')
    def report_content_page():
        kind = request.args.get('kind', '')
        share_id = request.args.get('id', '')
        if kind not in ('recap', 'flyer') or not share_id or len(share_id) > 200:
            abort(400)
        from content_safety import content_for_report
        row = content_for_report(kind, share_id)
        return page('report_content.html', content_kind=kind, content_id=share_id,
                    content_author=row.get('username') or '')

    @app.get('/admin/content-reports')
    @service.admin_required
    def content_reports_page():
        return page('content_reports.html')
