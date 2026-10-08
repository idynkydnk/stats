"""Plain-text edits and shared web/native remake responses."""
from flask import flash, jsonify, redirect, request, url_for
from bs4 import BeautifulSoup


def remake_response(message, endpoint, share_id, success=False, status=400):
    if request.is_json:
        return jsonify({'message' if success else 'error': message}), 200 if success else status
    flash(message, 'success' if success else 'error')
    query = {'published': 1} if endpoint == 'view_ai_recap' else {}
    return redirect(url_for(endpoint, share_id=share_id, **query))


def recap_summary(row):
    soup = BeautifulSoup(row.get('html_body') or '', 'html.parser')
    summary = soup.select_one('.summary-text')
    if summary is None:
        return ''
    for br in summary.find_all('br'):
        br.replace_with('\n')
    for paragraph in summary.find_all('p'):
        paragraph.insert_after('\n')
    return '\n'.join(line.strip() for line in summary.get_text().splitlines() if line.strip())


def edit_recap(row, data):
    """Keep images and stat tables, and insert edited text without interpreting HTML."""
    from email_content import plain_text_fallback_from_html
    soup = BeautifulSoup(row.get('html_body') or '', 'html.parser')
    updates = {}
    if 'title' in data and data['title'] != (row.get('subject') or ''):
        title = data['title'].strip()
        if not title:
            raise ValueError('Enter a recap title.')
        updates['subject'] = title
        for heading in (soup.find('h1'), soup.find('title')):
            if heading:
                heading.clear()
                heading.append(title)
    if 'summary' in data and data['summary'] != recap_summary(row):
        summary = soup.select_one('.summary-text')
        if summary is None:
            raise ValueError('This older recap cannot be edited directly. Remake its summary first.')
        if not data['summary'].strip():
            raise ValueError('Enter a recap summary.')
        summary.clear()
        for paragraph in data['summary'].strip().split('\n'):
            if paragraph.strip():
                node = soup.new_tag('p')
                node.string = paragraph.strip()
                summary.append(node)
        updates['html_body'] = str(soup)
    if updates:
        updates['html_body'] = str(soup)
        updates['plain_text_body'] = plain_text_fallback_from_html(updates['html_body'])
    return updates
