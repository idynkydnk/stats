"""HTML email bodies and AI summary payload builders for doubles, vollis, and other games.

Extracted from stats.py. These are pure content builders: they read games from the
database, call Gemini for the summary text, and return HTML/payload dicts. Sending
the email (Flask-Mail) stays in stats.py.
"""
import os
import base64
import uuid
from datetime import datetime

from flask import current_app

from other_functions import set_cur

SITE_BASE_URL = os.environ.get('SITE_BASE_URL', 'https://idynkydnk.pythonanywhere.com')

# Image models to try for AI email illustrations (separate quotas from text models).
GEMINI_IMAGE_MODELS = [
    ('gemini-2.5-flash-image', None),
    ('gemini-3.1-flash-image', '16:9'),
    ('gemini-3.1-flash-image-preview', '16:9'),
]
IMAGEN_FALLBACK_MODELS = [
    'imagen-4.0-fast-generate-001',
    'imagen-3.0-generate-002',
]


# Models to try in order. First is the best-quality current model (the
# 'flash-latest' alias tracks Google's newest stable Flash, currently 3.5).
# The rest are fallbacks with separate (and larger) free-tier quotas, so a
# daily 429 on one model no longer kills the feature.
GEMINI_MODELS = [
    'models/gemini-flash-latest',
    'models/gemini-3.1-flash-lite',
    'models/gemini-2.5-flash',
]


def generate_ai_text(prompt):
    """Generate text with Gemini, falling back to alternate models when the
    primary is rate-limited (429) or unavailable. Quotas are tracked per model,
    so a fallback usually succeeds even when the primary's daily cap is hit.

    Returns the generated text (stripped). Raises ValueError with all
    per-model errors if every model fails.
    """
    import google.generativeai as genai

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError('Gemini API key not configured.')
    genai.configure(api_key=api_key)

    errors = []
    for model_name in GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            try:
                text = (response.text or '') if hasattr(response, 'text') else ''
            except Exception:
                text = ''
            text = (text or '').strip()
            if text:
                return text
            errors.append(f'{model_name}: empty response')
        except Exception as e:
            errors.append(f'{model_name}: {e}')
    raise ValueError(f'AI summary generation failed on all models: {" | ".join(errors)}')


def _email_hero_styles():
    return """
                    .hero-image-card { padding: 0; overflow: hidden; text-align: center; }
                    .hero-image-card img { width: 100%; max-width: 600px; height: auto; display: block; border-radius: 12px; }
    """


def _email_hero_html(hero_image_url):
    if not hero_image_url:
        return ''
    return f"""
                    <div class="card hero-image-card">
                        <img src="{hero_image_url}" alt="AI game illustration">
                    </div>
    """


def _games_highlight_for_image(game_type, games, max_games=3):
    lines = []
    if game_type == 'doubles':
        for game in games[:max_games]:
            lines.append(
                f"{game[2]} & {game[3]} beat {game[5]} & {game[6]} ({game[4]}-{game[7]})"
            )
    elif game_type == 'vollis':
        for game in games[:max_games]:
            lines.append(f"{game[2]} beat {game[4]} ({game[3]}-{game[5]})")
    elif game_type == 'other':
        for game in games[:max_games]:
            winners = ', '.join(w['name'] for w in game.get('winners', []) if w.get('name'))
            losers = ', '.join(l['name'] for l in game.get('losers', []) if l.get('name'))
            game_name = game.get('game_name', 'game')
            lines.append(f"{winners} beat {losers} in {game_name}")
    return '; '.join(lines)


def _build_email_image_prompt(game_type, games, summary, player_names):
    sport_desc = {
        'doubles': 'beach volleyball doubles match on sand courts',
        'vollis': 'intense one-on-one vollis volleyball rally',
        'other': 'fun recreational sports game session',
    }.get(game_type, 'sports games')
    names = ', '.join(sorted(player_names)[:10])
    highlight = _games_highlight_for_image(game_type, games)
    summary_snip = (summary or '')[:300]
    return f"""Create a vibrant cartoon illustration for a sports recap email.

Sport scene: {sport_desc}
Key results: {highlight}
Mood from recap: {summary_snip}

Include these players as stylized cartoon characters with bold, expressive animated-cartoon faces (exaggerated emotions, big eyes, dynamic poses). Use fun generic cartoon avatars — NOT photorealistic, do NOT depict real people's likenesses.

Composition: 2-panel comic strip in one wide image showing the dramatic rally moment and the celebration aftermath. Motion lines, energy effects, saturated colors, sports-anime highlight reel energy.

No text, letters, numbers, captions, watermarks, or logos. Landscape 16:9 friendly framing.
Players to feature: {names}"""


def _image_bytes_from_genai_response(response):
    """Pull inline image bytes from a google.generativeai response."""
    if not getattr(response, 'candidates', None):
        pf = getattr(response, 'prompt_feedback', None)
        raise ValueError(f'no candidates (prompt_feedback={pf})')
    notes = []
    for candidate in response.candidates:
        content = getattr(candidate, 'content', None)
        parts = getattr(content, 'parts', None) or []
        for part in parts:
            inline = getattr(part, 'inline_data', None)
            if inline and getattr(inline, 'data', None):
                mime = getattr(inline, 'mime_type', None) or 'image/png'
                data = inline.data
                if isinstance(data, str):
                    data = base64.b64decode(data)
                return data, mime
        notes.append(str(getattr(candidate, 'finish_reason', 'unknown')))
    raise ValueError(f'no image in response ({", ".join(notes)})')


def _generate_image_bytes_genai(prompt, api_key):
    """Generate image using google.generativeai (same SDK as text summaries)."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    errors = []
    model_names = [
        'models/gemini-2.5-flash-image',
        'models/gemini-3.1-flash-image',
        'models/gemini-3.1-flash-image-preview',
    ]
    for model_name in model_names:
        try:
            model = genai.GenerativeModel(model_name)
            for modalities in (['IMAGE'], ['TEXT', 'IMAGE']):
                try:
                    response = model.generate_content(
                        prompt,
                        generation_config={'response_modalities': modalities},
                    )
                    return _image_bytes_from_genai_response(response)
                except Exception as inner:
                    errors.append(f'{model_name} {modalities}: {inner}')
        except Exception as e:
            errors.append(f'{model_name}: {e}')
    raise ValueError('genai: ' + ' | '.join(errors))


def _rest_error_detail(resp):
    try:
        data = resp.json()
        return data.get('error', {}).get('message') or resp.text[:300]
    except Exception:
        return resp.text[:300] if resp.text else f'HTTP {resp.status_code}'


def _generate_image_bytes_rest(prompt, api_key):
    """Generate one image via Gemini REST API. Returns (bytes, mime_type)."""
    import requests

    errors = []
    headers = {'x-goog-api-key': api_key, 'Content-Type': 'application/json'}

    for model, model_aspect in GEMINI_IMAGE_MODELS:
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
        for modalities in (['IMAGE'], ['TEXT', 'IMAGE']):
            generation_config = {'responseModalities': modalities}
            if model_aspect:
                generation_config['imageConfig'] = {'aspectRatio': model_aspect}
            payload = {
                'contents': [{'parts': [{'text': prompt}]}],
                'generationConfig': generation_config,
            }
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=120)
                if resp.status_code == 429:
                    errors.append(f'{model}: rate limited')
                    break
                if resp.status_code >= 400:
                    errors.append(f'{model} {modalities}: {_rest_error_detail(resp)}')
                    continue
                data = resp.json()
                pf = data.get('promptFeedback') or data.get('prompt_feedback') or {}
                block = pf.get('blockReason') or pf.get('block_reason')
                if block:
                    errors.append(f'{model}: blocked ({block})')
                    continue
                for candidate in data.get('candidates', []):
                    for part in candidate.get('content', {}).get('parts', []):
                        inline = part.get('inlineData') or part.get('inline_data')
                        if inline and inline.get('data'):
                            raw = base64.b64decode(inline['data'])
                            mime = inline.get('mimeType') or inline.get('mime_type') or 'image/png'
                            return raw, mime
                fr = ''
                if data.get('candidates'):
                    fr = data['candidates'][0].get('finishReason') or data['candidates'][0].get('finish_reason') or ''
                errors.append(f'{model} {modalities}: no image (finish={fr})')
            except Exception as e:
                errors.append(f'{model} {modalities}: {e}')

    for imagen_model in IMAGEN_FALLBACK_MODELS:
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{imagen_model}:predict'
        payload = {
            'instances': [{'prompt': prompt}],
            'parameters': {'sampleCount': 1},
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            if resp.status_code == 429:
                errors.append(f'{imagen_model}: rate limited')
                continue
            if resp.status_code >= 400:
                errors.append(f'{imagen_model}: {_rest_error_detail(resp)}')
                continue
            data = resp.json()
            for pred in data.get('predictions', []):
                b64 = pred.get('bytesBase64Encoded') or pred.get('bytes_base64_encoded')
                if b64:
                    mime = pred.get('mimeType') or pred.get('mime_type') or 'image/png'
                    return base64.b64decode(b64), mime
            errors.append(f'{imagen_model}: no image in response')
        except Exception as e:
            errors.append(f'{imagen_model}: {e}')

    raise ValueError(' | '.join(errors))


def _generate_image_bytes(prompt, api_key):
    """Try SDK first, then REST/Imagen fallbacks."""
    errors = []
    try:
        return _generate_image_bytes_genai(prompt, api_key)
    except Exception as e:
        errors.append(str(e))
    try:
        return _generate_image_bytes_rest(prompt, api_key)
    except Exception as e:
        errors.append(str(e))
    raise ValueError(' || '.join(errors))


def _save_email_image(image_bytes, ext):
    base = os.path.dirname(os.path.abspath(__file__))
    dest_dir = os.path.join(base, 'static', 'email_images')
    os.makedirs(dest_dir, exist_ok=True)
    filename = f'{uuid.uuid4().hex}.{ext}'
    abs_path = os.path.join(dest_dir, filename)
    with open(abs_path, 'wb') as f:
        f.write(image_bytes)
    return f'{SITE_BASE_URL}/static/email_images/{filename}'


def generate_email_hero_image(api_key, game_type, games, summary, player_names):
    """Generate a cartoon illustration for the AI email hero image."""
    prompt = _build_email_image_prompt(game_type, games, summary, player_names)
    raw, mime = _generate_image_bytes(prompt, api_key)
    if 'gif' in mime:
        ext = 'gif'
    elif 'jpeg' in mime or 'jpg' in mime:
        ext = 'jpg'
    else:
        ext = 'png'
    return _save_email_image(raw, ext)


def _try_generate_email_hero_image(api_key, game_type, games, summary, player_names):
    try:
        return generate_email_hero_image(api_key, game_type, games, summary, player_names), None
    except Exception as e:
        err = str(e)
        try:
            current_app.logger.warning('AI email image generation failed: %s', err)
        except Exception:
            pass
        return None, err


def email_html_for_inline_preview(html_body):
    """Extract email body with scoped styles for inline display on the preview page."""
    import re
    from bs4 import BeautifulSoup

    if not html_body or not str(html_body).strip():
        return '<p>No email content.</p>'

    soup = BeautifulSoup(html_body, 'html.parser')
    styles = []
    for tag in soup.find_all('style'):
        css = tag.get_text() or ''
        css = re.sub(r'\bbody\b', '.sr-email-inline', css)
        css = re.sub(r'\bhtml\b', '.sr-email-inline', css)
        styles.append(css)
    body = soup.find('body')
    content = body.decode_contents() if body else html_body
    style_block = f'<style>{"".join(styles)}</style>' if styles else ''
    return f'{style_block}<div class="sr-email-inline">{content}</div>'


def format_name_for_email(name):
    if not name:
        return ""
    name = str(name).strip()
    if not name:
        return ""
    if ' ' in name:
        first, rest = name.split(' ', 1)
        return f"{first}<br>{rest}"
    if len(name) > 10:
        mid = len(name) // 2
        return f"{name[:mid]}<br>{name[mid:]}"
    return f"{name}<br>&nbsp;"


def create_doubles_email_html(summary, stats, games, date_obj, hero_image_url=None):
    summary_html = summary.replace(chr(10), '<br>') if summary else ''
    formatted_date = date_obj.strftime('%m/%d/%Y')
    hero_styles = _email_hero_styles() if hero_image_url else ''
    hero_block = _email_hero_html(hero_image_url)

    html_body = f"""
            <html>
            <head>
                <style>
                    body {{ 
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                        background-color: #0b0f14;
                        color: #e4e8eb;
                        padding: 20px;
                        line-height: 1.6;
                        margin: 0;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                    }}
                    h1 {{
                        color: #66d9ef;
                        text-align: center;
                        margin-bottom: 24px;
                        font-size: 22px;
                        font-weight: 600;
                    }}
                    .card {{
                        background: #131a24;
                        border-radius: 12px;
                        padding: 20px;
                        margin-bottom: 16px;
                        border: 1px solid rgba(255, 255, 255, 0.08);
                    }}
                    .card h2 {{
                        margin-top: 0;
                        padding-bottom: 12px;
                        font-size: 14px;
                        font-weight: 600;
                        margin-bottom: 16px;
                        text-transform: uppercase;
                        letter-spacing: 1px;
                        color: #66d9ef;
                        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                    }}
                    .summary-text {{
                        background: rgba(11, 15, 20, 0.5);
                        border-radius: 8px;
                        padding: 16px;
                        border: 1px solid rgba(255, 255, 255, 0.06);
                        color: #e4e8eb;
                        line-height: 1.7;
                        font-size: 14px;
                    }}
                    .stats-table {{
                        width: 100%;
                        border-collapse: collapse;
                        color: #e4e8eb;
                        font-size: 13px;
                    }}
                    .stats-table thead {{
                        background: rgba(255, 255, 255, 0.03);
                    }}
                    .stats-table th {{
                        padding: 10px 8px;
                        text-align: center;
                        font-size: 11px;
                        font-weight: 600;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                        color: #8b949e;
                    }}
                    .stats-table td {{
                        padding: 10px 8px;
                        text-align: center;
                        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                    }}
                    .stats-table tbody tr:last-child td {{
                        border-bottom: none;
                    }}
                    .stats-table tbody tr:nth-child(odd) {{
                        background: rgba(255, 255, 255, 0.02);
                    }}
                    .stats-rank {{
                        width: 30px;
                        font-weight: 600;
                        color: #66d9ef;
                    }}
                    .stats-player {{
                        text-align: left !important;
                        font-weight: 500;
                    }}
                    .diff-positive {{
                        color: #4ade80;
                        font-weight: 600;
                    }}
                    .diff-negative {{
                        color: #f87171;
                        font-weight: 600;
                    }}
                    .games-table {{
                        width: 100%;
                        border-collapse: collapse;
                        color: #e4e8eb;
                        font-size: 13px;
                    }}
                    .games-table thead {{
                        background: rgba(255, 255, 255, 0.03);
                    }}
                    .games-table th {{
                        padding: 10px 6px;
                        text-align: center;
                        font-size: 11px;
                        font-weight: 600;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                        color: #8b949e;
                    }}
                    .games-table td {{
                        padding: 10px 6px;
                        text-align: center;
                        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                        vertical-align: middle;
                    }}
                    .games-table tbody tr:last-child td {{
                        border-bottom: none;
                    }}
                    .games-table tbody tr:nth-child(odd) {{
                        background: rgba(255, 255, 255, 0.02);
                    }}
                    .time-cell {{
                        font-size: 12px;
                        color: #8b949e;
                    }}
                    .team-cell {{
                        text-align: center;
                    }}
                    .winner-team {{
                        color: #4ade80;
                    }}
                    .loser-team {{
                        color: #f87171;
                    }}
                    .player-name {{
                        font-size: 13px;
                        font-weight: 500;
                        display: block;
                        line-height: 1.4;
                    }}
                    .score-winner {{
                        color: #4ade80;
                        font-weight: 700;
                        font-size: 15px;
                    }}
                    .score-loser {{
                        color: #f87171;
                        font-weight: 700;
                        font-size: 15px;
                    }}
                    .footer {{
                        text-align: center;
                        margin-top: 24px;
                        padding-top: 20px;
                        border-top: 1px solid rgba(255, 255, 255, 0.08);
                    }}
                    .link-button {{
                        display: inline-block;
                        background-color: #66d9ef;
                        color: #0b0f14;
                        padding: 12px 24px;
                        border-radius: 8px;
                        text-decoration: none;
                        font-weight: 600;
                        font-size: 14px;
                    }}
                    .opt-in-section {{
                        margin-top: 16px;
                        padding-top: 16px;
                        border-top: 1px solid rgba(255, 255, 255, 0.05);
                    }}
                    .opt-in-text {{
                        color: #8b949e;
                        font-size: 13px;
                        margin-bottom: 10px;
                    }}
                    .opt-in-button {{
                        display: inline-block;
                        background-color: rgba(102, 217, 239, 0.15);
                        color: #66d9ef;
                        padding: 10px 20px;
                        border-radius: 6px;
                        text-decoration: none;
                        font-weight: 500;
                        font-size: 13px;
                        border: 1px solid rgba(102, 217, 239, 0.3);
                    }}
                    {hero_styles}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Volleyball Recap - {formatted_date}</h1>
                    {hero_block}
                    
                    <div class="card">
                        <h2>AI Summary</h2>
                        <div class="summary-text">
                            {summary_html}
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2>Player Stats</h2>
                        <table class="stats-table">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>Player</th>
                                    <th>W</th>
                                    <th>L</th>
                                    <th>Win %</th>
                                    <th>+/-</th>
                                </tr>
                            </thead>
                            <tbody>
            """

    for index, stat in enumerate(stats, start=1):
        player_name = stat[0]
        wins = stat[1]
        losses = stat[2]
        win_pct = stat[3] * 100
        differential = stat[4]
        diff_sign = '+' if differential >= 0 else ''

        if differential > 0:
            diff_class = "diff-positive"
        elif differential < 0:
            diff_class = "diff-negative"
        else:
            diff_class = ""

        html_body += f"""
                                <tr>
                                    <td class="stats-rank">{index}</td>
                                    <td class="stats-player">{format_name_for_email(player_name)}</td>
                                    <td>{wins}</td>
                                    <td>{losses}</td>
                                    <td>{win_pct:.0f}%</td>
                                    <td class="{diff_class}">{diff_sign}{differential}</td>
                                </tr>
                """

    html_body += """
                            </tbody>
                        </table>
                    </div>
                    
                    <div class="card">
                        <h2>Games (""" + str(len(games)) + """)</h2>
                        <table class="games-table">
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Winners</th>
                                    <th></th>
                                    <th>Losers</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
            """

    for game in games:
        time_display = ""
        if len(game) > 1 and game[1]:
            date_time_str = str(game[1]).strip()
            parts = date_time_str.split()
            if len(parts) > 1:
                time_display = " ".join(parts[1:]).strip()
            elif parts:
                time_display = parts[0]
        if not time_display:
            time_display = "-"

        winner1 = format_name_for_email(game[2]) if game[2] else ""
        winner2 = format_name_for_email(game[3]) if game[3] else ""
        loser1 = format_name_for_email(game[5]) if game[5] else ""
        loser2 = format_name_for_email(game[6]) if game[6] else ""

        winner_score = game[4] if len(game) > 4 and game[4] is not None else ""
        loser_score = game[7] if len(game) > 7 and game[7] is not None else ""

        html_body += f"""
                                <tr>
                                    <td class="time-cell">{time_display}</td>
                                    <td class="team-cell winner-team"><span class="player-name">{winner1}</span><span class="player-name">{winner2}</span></td>
                                    <td class="score-winner">{winner_score}</td>
                                    <td class="team-cell loser-team"><span class="player-name">{loser1}</span><span class="player-name">{loser2}</span></td>
                                    <td class="score-loser">{loser_score}</td>
                                </tr>
                """

    html_body += """
                            </tbody>
                        </table>
                    </div>
            """

    stats_year = date_obj.year

    html_body += f"""
                    <div class="footer">
                        <a href="https://idynkydnk.pythonanywhere.com/stats/{stats_year}/" class="link-button">View {stats_year} Stats</a>
                        <div class="opt-in-section">
                            <p class="opt-in-text">Want all future AI summaries?</p>
                            <a href="https://idynkydnk.pythonanywhere.com/opt_in_ai_emails?email={{{{EMAIL_PLACEHOLDER}}}}" class="opt-in-button">Yes, include me</a>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """

    return html_body


def build_doubles_email_payload(selected_game_ids, prompt_style='announcer', custom_prompt=''):
    from stat_functions import calculate_stats_from_games, get_current_streaks_last_365_days, convert_ampm
    from player_functions import get_player_by_name

    # Define different prompt styles
    PROMPT_STYLES = {
        'announcer': """You are an energetic sports announcer writing an exciting recap email.
Use dramatic language, exciting calls, and hype up big plays and close games.
Write like you're doing live ESPN commentary - high energy, dramatic pauses, and memorable catchphrases.
Make readers feel the excitement of being there. Use short punchy sentences mixed with longer dramatic buildups.
Keep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only. No long blocks of text.""",

        'analyst': """You are a data-driven sports analyst writing a statistical breakdown email.
Focus on the numbers: win percentages, point differentials, streaks, and trends.
Draw insights from the statistics and explain what they mean for each player's performance.
Be precise and factual, but still engaging. Reference specific stats to back up your observations.
Keep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only. No long blocks of text.""",

        'storyteller': """You are a sports storyteller writing a narrative recap email.
Weave the games into an engaging story with character development and dramatic tension.
Create narrative arcs - underdogs rising, champions defending, rivalries intensifying.
Use vivid imagery and build suspense. Make readers feel emotionally invested in the outcomes.
Keep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only. No long blocks of text.""",

        'comedian': """You are a comedy writer doing a sports recap email.
Be playful, witty, and don't be afraid to gently roast players (in good fun).
Find the humor in the games - funny moments, ironic outcomes, playful observations.
Keep it lighthearted and fun. Everyone should laugh, including those being teased.
Keep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only. No long blocks of text.""",

        'roast': """You are a brutal roast comedian writing a savage recap email.
Show absolutely NO mercy. Destroy everyone's performance with brutal honesty and savage insults.
Mock the winners for barely winning, demolish the losers for their failures.
Be creative with your insults - reference specific plays, scores, and failures.
This is all in good fun but don't hold back. Make it hurt (but funny).
Keep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only. No long blocks of text.""",

    }

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError('Gemini API key not configured.')

    if not current_app.config['MAIL_USERNAME'] or not current_app.config['MAIL_PASSWORD']:
        raise ValueError('Email not configured.')

    if not selected_game_ids:
        raise ValueError('No games selected.')

    # Fetch selected games by ID
    cur = set_cur()
    placeholders = ','.join('?' * len(selected_game_ids))
    cur.execute(f"SELECT * FROM games WHERE id IN ({placeholders}) ORDER BY game_date DESC", 
                [int(gid) for gid in selected_game_ids])
    raw_games = cur.fetchall()
    
    if not raw_games:
        raise ValueError('None of the selected games were found.')
    
    games = convert_ampm(raw_games)
    stats = calculate_stats_from_games(games)

    all_streaks = get_current_streaks_last_365_days()
    streaks_dict = {streak[0]: {'length': streak[1], 'type': streak[2], 'max': streak[3]} for streak in all_streaks}

    # Get date range from selected games
    game_dates = sorted(set(game[1].split(' ')[0] for game in games))
    if len(game_dates) == 1:
        date_str = game_dates[0]
    else:
        date_str = f"{game_dates[0]} to {game_dates[-1]}"
    
    context = f"Date: {date_str}\n"
    context += f"Total Games: {len(games)}\n\n"
    
    # Helper to parse height string like "5'10"" or "6'2"" to inches
    def parse_height_to_inches(height_str):
        if not height_str:
            return None
        try:
            # Handle formats like 5'10" or 5'10
            height_str = height_str.replace('"', '').replace("'", ' ').strip()
            parts = height_str.split()
            if len(parts) >= 2:
                feet = int(parts[0])
                inches = int(parts[1])
                return feet * 12 + inches
            elif len(parts) == 1:
                return int(parts[0]) * 12  # Just feet
        except:
            pass
        return None
    
    # Helper to calculate actual age (accounting for whether birthday has passed)
    def calculate_age(birth_date_str):
        try:
            birth_date = datetime.strptime(birth_date_str[:10], '%Y-%m-%d')
            today = datetime.now()
            age = today.year - birth_date.year
            # Subtract 1 if birthday hasn't occurred yet this year
            if (today.month, today.day) < (birth_date.month, birth_date.day):
                age -= 1
            return age
        except:
            return None
    
    # First pass: collect all player heights and ages to find outliers
    player_heights = {}
    player_ages = {}
    for stat in stats[:10]:
        player_name = stat[0]
        player_info = get_player_by_name(player_name)
        if player_info:
            if player_info[4]:
                height_inches = parse_height_to_inches(player_info[4])
                if height_inches:
                    player_heights[player_name] = (height_inches, player_info[4])
            if player_info[3]:
                age = calculate_age(player_info[3])
                if age:
                    player_ages[player_name] = age
    
    # Only mention height if there's a significant outlier (4+ inches from average)
    height_outliers = set()
    if len(player_heights) >= 2:
        heights = [h[0] for h in player_heights.values()]
        avg_height = sum(heights) / len(heights)
        for player_name, (height_inches, _) in player_heights.items():
            if abs(height_inches - avg_height) >= 4:
                height_outliers.add(player_name)
    
    # Only mention age if there's a significant outlier (10+ years from average)
    age_outliers = set()
    if len(player_ages) >= 2:
        ages = list(player_ages.values())
        avg_age = sum(ages) / len(ages)
        for player_name, age in player_ages.items():
            if abs(age - avg_age) >= 10:
                age_outliers.add(player_name)
    
    context += "Player Stats (with details & streaks):\n"
    for stat in stats[:10]:
        player_name = stat[0]
        wins = stat[1]
        losses = stat[2]
        win_pct = stat[3] * 100
        differential = stat[4]

        player_info = get_player_by_name(player_name)
        age_str = ""
        height_str = ""
        if player_info:
            # Only include age if this player is a notable outlier (10+ years from avg)
            if player_name in age_outliers and player_name in player_ages:
                age_str = f", Age: {player_ages[player_name]}"
            # Only include height if this player is a notable outlier (4+ inches from avg)
            if player_name in height_outliers and player_info[4]:
                height_str = f", Height: {player_info[4]}"

        streak_str = ""
        if player_name in streaks_dict:
            streak_info = streaks_dict[player_name]
            # Only mention streaks of 3+ games - shorter isn't interesting
            if streak_info['length'] >= 3:
                streak_str = f", Current Streak: {streak_info['length']} {streak_info['type']}s"

        # Only show point differential if it's significant (+/- 5 or more)
        diff_str = f", Point Diff: {differential:+d}" if abs(differential) >= 5 else ""
        context += f"- {player_name}: {wins}-{losses} ({win_pct:.1f}%){diff_str}{age_str}{height_str}{streak_str}\n"

    # Get earliest game date for historical queries
    date_values = [r[1] for r in raw_games if len(r) > 1 and r[1]]
    earliest_game_date = min(date_values) if date_values else (games[0][1].split()[0] if games else datetime.now().strftime('%Y-%m-%d'))
    
    context += "\nHistorical Context:\n"
    for game in games[:5]:
        team1 = (game[2], game[3])
        team2 = (game[5], game[6])

        cur.execute("""
                SELECT COUNT(*) FROM games 
                WHERE ((winner1 = ? AND winner2 = ?) OR (winner1 = ? AND winner2 = ?))
                  AND ((loser1 = ? AND loser2 = ?) OR (loser1 = ? AND loser2 = ?))
                  AND game_date < ?
            """, (team1[0], team1[1], team1[1], team1[0], 
                  team2[0], team2[1], team2[1], team2[0], earliest_game_date))
        team1_wins = cur.fetchone()[0]

        cur.execute("""
                SELECT COUNT(*) FROM games 
                WHERE ((winner1 = ? AND winner2 = ?) OR (winner1 = ? AND winner2 = ?))
                  AND ((loser1 = ? AND loser2 = ?) OR (loser1 = ? AND loser2 = ?))
                  AND game_date < ?
            """, (team2[0], team2[1], team2[1], team2[0],
                  team1[0], team1[1], team1[1], team1[0], earliest_game_date))
        team2_wins = cur.fetchone()[0]

        # Only mention historical record if teams have played 3+ times
        total_games = team1_wins + team2_wins
        if total_games >= 3:
            context += f"- {team1[0]} & {team1[1]} vs {team2[0]} & {team2[1]}: Historical record {team1_wins}-{team2_wins}\n"

    context += "\nGames Played (in chronological order):\n"
    for game in reversed(games[:10]):
        winners = f"{game[2]} & {game[3]}"
        losers = f"{game[5]} & {game[6]}"
        score = f"{game[4]}-{game[7]}"
        comment_str = ""
        if len(game) > 9 and game[9]:
            comment_str = f" - Comment: {game[9]}"
        context += f"- {winners} def. {losers} ({score}){comment_str}\n"

    # Get the prompt style instructions
    if prompt_style == 'custom' and custom_prompt.strip():
        style_instructions = custom_prompt.strip() + "\nKeep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only."
    else:
        style_instructions = PROMPT_STYLES.get(prompt_style, PROMPT_STYLES['announcer'])
    
    prompt = f"""{style_instructions}

Write in clean, professional sentences—no bullet points, asterisks, emojis, or decorative quotation marks.
Only quote a comment if it is already in the data enclosed in quotation marks.
Weave any comments smoothly into the narrative.
CRITICAL: Keep each paragraph to 2-3 sentences. Aim for under 100 words total. Be concise—readers will skim, not read long text.

Here is the game data:

{context}

Write the recap:"""
    summary = generate_ai_text(prompt)

    players_set = set()
    for game in games:
        for player_name in [game[2], game[3], game[5], game[6]]:
            if player_name and player_name.strip():
                players_set.add(player_name)

    players = []
    players_without_email = []
    for player_name in players_set:
        player_info = get_player_by_name(player_name)
        if player_info and player_info[2]:
            players.append({'name': player_name, 'email': player_info[2]})
        else:
            players_without_email.append(player_name)

    all_emails = [player['email'] for player in players]
    
    # Add emails from players who opted in to receive all AI emails
    cur = set_cur()
    cur.execute("SELECT email FROM players WHERE email IS NOT NULL AND notes LIKE ?", ('%AI_EMAILS_OPT_IN%',))
    opted_in_players = cur.fetchall()
    for opt_in_player in opted_in_players:
        opt_in_email = opt_in_player[0]
        if opt_in_email and opt_in_email not in all_emails:
            all_emails.append(opt_in_email)

    # Parse earliest game date for email subject (raw DB is YYYY-MM-DD; fallback may be MM/DD/YYYY)
    try:
        date_obj = datetime.strptime(str(earliest_game_date)[:10], '%Y-%m-%d')
    except ValueError:
        try:
            date_obj = datetime.strptime(str(earliest_game_date)[:10], '%m/%d/%Y')
        except ValueError:
            date_obj = datetime.now()
    formatted_date = date_obj.strftime('%m/%d/%y')

    hero_image_url, hero_image_error = _try_generate_email_hero_image(
        api_key, 'doubles', games, summary, players_set,
    )
    html_body = create_doubles_email_html(
        summary, stats, games, date_obj, hero_image_url=hero_image_url,
    )
    subject = f"Vball Summary - {formatted_date}"

    summary_preview = summary[:150] + "..." if len(summary) > 150 else summary

    return {
        'date': date_str,
        'games': games,
        'stats': stats,
        'summary': summary,
        'summary_preview': summary_preview,
        'context': context,
        'players': players,
        'players_without_email': players_without_email,
        'all_emails': all_emails,
        'html_body': html_body,
        'subject': subject,
        'hero_image_url': hero_image_url,
        'hero_image_error': hero_image_error,
        'date_obj': date_obj,
        'formatted_date': formatted_date
    }


def create_vollis_email_html(summary, stats, games, date_obj, hero_image_url=None):
    summary_html = summary.replace(chr(10), '<br>') if summary else ''
    formatted_date = date_obj.strftime('%m/%d/%Y')
    hero_styles = _email_hero_styles() if hero_image_url else ''
    hero_block = _email_hero_html(hero_image_url)

    html_body = f"""
            <html>
            <head>
                <style>
                    body {{ 
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                        background-color: #0b0f14;
                        color: #e4e8eb;
                        padding: 20px;
                        line-height: 1.6;
                        margin: 0;
                    }}
                    .container {{ max-width: 600px; margin: 0 auto; }}
                    h1 {{ color: #66d9ef; text-align: center; margin-bottom: 24px; font-size: 22px; font-weight: 600; }}
                    .card {{ background: #131a24; border-radius: 12px; padding: 20px; margin-bottom: 16px; border: 1px solid rgba(255, 255, 255, 0.08); }}
                    .card h2 {{ margin-top: 0; padding-bottom: 12px; font-size: 14px; font-weight: 600; margin-bottom: 16px; text-transform: uppercase; letter-spacing: 1px; color: #66d9ef; border-bottom: 1px solid rgba(255, 255, 255, 0.1); }}
                    .summary-text {{ background: rgba(11, 15, 20, 0.5); border-radius: 8px; padding: 16px; border: 1px solid rgba(255, 255, 255, 0.06); color: #e4e8eb; line-height: 1.7; font-size: 14px; }}
                    .stats-table {{ width: 100%; border-collapse: collapse; color: #e4e8eb; font-size: 13px; }}
                    .stats-table thead {{ background: rgba(255, 255, 255, 0.03); }}
                    .stats-table th {{ padding: 10px 8px; text-align: center; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: #8b949e; }}
                    .stats-table td {{ padding: 10px 8px; text-align: center; border-bottom: 1px solid rgba(255, 255, 255, 0.05); }}
                    .stats-table tbody tr:last-child td {{ border-bottom: none; }}
                    .stats-table tbody tr:nth-child(odd) {{ background: rgba(255, 255, 255, 0.02); }}
                    .stats-rank {{ width: 30px; font-weight: 600; color: #66d9ef; }}
                    .stats-player {{ text-align: left !important; font-weight: 500; }}
                    .games-table {{ width: 100%; border-collapse: collapse; color: #e4e8eb; font-size: 13px; }}
                    .games-table thead {{ background: rgba(255, 255, 255, 0.03); }}
                    .games-table th {{ padding: 10px 6px; text-align: center; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: #8b949e; }}
                    .games-table td {{ padding: 10px 6px; text-align: center; border-bottom: 1px solid rgba(255, 255, 255, 0.05); vertical-align: middle; }}
                    .games-table tbody tr:last-child td {{ border-bottom: none; }}
                    .games-table tbody tr:nth-child(odd) {{ background: rgba(255, 255, 255, 0.02); }}
                    .time-cell {{ font-size: 12px; color: #8b949e; }}
                    .winner-team {{ color: #4ade80; }}
                    .loser-team {{ color: #f87171; }}
                    .player-name {{ font-size: 13px; font-weight: 500; display: block; line-height: 1.4; }}
                    .score-winner {{ color: #4ade80; font-weight: 700; font-size: 15px; }}
                    .score-loser {{ color: #f87171; font-weight: 700; font-size: 15px; }}
                    .footer {{ text-align: center; margin-top: 24px; padding-top: 20px; border-top: 1px solid rgba(255, 255, 255, 0.08); }}
                    .link-button {{ display: inline-block; background-color: #66d9ef; color: #0b0f14; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px; }}
                    .opt-in-section {{ margin-top: 16px; padding-top: 16px; border-top: 1px solid rgba(255, 255, 255, 0.05); }}
                    .opt-in-text {{ color: #8b949e; font-size: 13px; margin-bottom: 10px; }}
                    .opt-in-button {{ display: inline-block; background-color: rgba(102, 217, 239, 0.15); color: #66d9ef; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 500; font-size: 13px; border: 1px solid rgba(102, 217, 239, 0.3); }}
                    {hero_styles}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Vollis Recap - {formatted_date}</h1>
                    {hero_block}
                    
                    <div class="card">
                        <h2>AI Summary</h2>
                        <div class="summary-text">
                            {summary_html}
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2>Player Stats</h2>
                        <table class="stats-table">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>Player</th>
                                    <th>W</th>
                                    <th>L</th>
                                    <th>Win %</th>
                                </tr>
                            </thead>
                            <tbody>
            """

    for index, stat in enumerate(stats, start=1):
        player_name = stat[0]
        wins = stat[1]
        losses = stat[2]
        win_pct = stat[3] * 100

        html_body += f"""
                                <tr>
                                    <td class="stats-rank">{index}</td>
                                    <td class="stats-player">{format_name_for_email(player_name)}</td>
                                    <td>{wins}</td>
                                    <td>{losses}</td>
                                    <td>{win_pct:.0f}%</td>
                                </tr>
                """

    html_body += """
                            </tbody>
                        </table>
                    </div>
                    
                    <div class="card">
                        <h2>Games (""" + str(len(games)) + """)</h2>
                        <table class="games-table">
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Winner</th>
                                    <th></th>
                                    <th>Loser</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
            """

    for game in games:
        time_display = ""
        if len(game) > 1 and game[1]:
            date_time_str = str(game[1]).strip()
            parts = date_time_str.split()
            if len(parts) > 1:
                time_display = " ".join(parts[1:]).strip()
            elif parts:
                time_display = parts[0]
        if not time_display:
            time_display = "-"

        winner = format_name_for_email(game[2]) if game[2] else ""
        loser = format_name_for_email(game[4]) if game[4] else ""
        winner_score = game[3] if len(game) > 3 and game[3] is not None else ""
        loser_score = game[5] if len(game) > 5 and game[5] is not None else ""

        html_body += f"""
                                <tr>
                                    <td class="time-cell">{time_display}</td>
                                    <td class="winner-team"><span class="player-name">{winner}</span></td>
                                    <td class="score-winner">{winner_score}</td>
                                    <td class="loser-team"><span class="player-name">{loser}</span></td>
                                    <td class="score-loser">{loser_score}</td>
                                </tr>
                """

    stats_year = date_obj.year
    html_body += f"""
                            </tbody>
                        </table>
                    </div>
                    <div class="footer">
                        <a href="https://idynkydnk.pythonanywhere.com/vollis_stats/{stats_year}/" class="link-button">View {stats_year} Vollis Stats</a>
                        <div class="opt-in-section">
                            <p class="opt-in-text">Want all future AI summaries?</p>
                            <a href="https://idynkydnk.pythonanywhere.com/opt_in_ai_emails?email={{{{EMAIL_PLACEHOLDER}}}}" class="opt-in-button">Yes, include me</a>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """

    return html_body


def create_other_email_html(summary, stats, games, date_obj, game_name_label='', hero_image_url=None):
    summary_html = summary.replace(chr(10), '<br>') if summary else ''
    formatted_date = date_obj.strftime('%m/%d/%Y')
    title_suffix = f" ({game_name_label})" if game_name_label else ""
    hero_styles = _email_hero_styles() if hero_image_url else ''
    hero_block = _email_hero_html(hero_image_url)

    html_body = f"""
            <html>
            <head>
                <style>
                    body {{ 
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                        background-color: #0b0f14;
                        color: #e4e8eb;
                        padding: 20px;
                        line-height: 1.6;
                        margin: 0;
                    }}
                    .container {{ max-width: 600px; margin: 0 auto; }}
                    h1 {{ color: #66d9ef; text-align: center; margin-bottom: 24px; font-size: 22px; font-weight: 600; }}
                    .card {{ background: #131a24; border-radius: 12px; padding: 20px; margin-bottom: 16px; border: 1px solid rgba(255, 255, 255, 0.08); }}
                    .card h2 {{ margin-top: 0; padding-bottom: 12px; font-size: 14px; font-weight: 600; margin-bottom: 16px; text-transform: uppercase; letter-spacing: 1px; color: #66d9ef; border-bottom: 1px solid rgba(255, 255, 255, 0.1); }}
                    .summary-text {{ background: rgba(11, 15, 20, 0.5); border-radius: 8px; padding: 16px; border: 1px solid rgba(255, 255, 255, 0.06); color: #e4e8eb; line-height: 1.7; font-size: 14px; }}
                    .stats-table {{ width: 100%; border-collapse: collapse; color: #e4e8eb; font-size: 13px; }}
                    .stats-table thead {{ background: rgba(255, 255, 255, 0.03); }}
                    .stats-table th {{ padding: 10px 8px; text-align: center; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: #8b949e; }}
                    .stats-table td {{ padding: 10px 8px; text-align: center; border-bottom: 1px solid rgba(255, 255, 255, 0.05); }}
                    .stats-table tbody tr:last-child td {{ border-bottom: none; }}
                    .stats-table tbody tr:nth-child(odd) {{ background: rgba(255, 255, 255, 0.02); }}
                    .stats-rank {{ width: 30px; font-weight: 600; color: #66d9ef; }}
                    .stats-player {{ text-align: left !important; font-weight: 500; }}
                    .games-table {{ width: 100%; border-collapse: collapse; color: #e4e8eb; font-size: 13px; }}
                    .games-table thead {{ background: rgba(255, 255, 255, 0.03); }}
                    .games-table th {{ padding: 10px 6px; text-align: center; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: #8b949e; }}
                    .games-table td {{ padding: 10px 6px; text-align: center; border-bottom: 1px solid rgba(255, 255, 255, 0.05); vertical-align: middle; }}
                    .games-table tbody tr:last-child td {{ border-bottom: none; }}
                    .games-table tbody tr:nth-child(odd) {{ background: rgba(255, 255, 255, 0.02); }}
                    .time-cell {{ font-size: 12px; color: #8b949e; }}
                    .winner-team {{ color: #4ade80; }}
                    .loser-team {{ color: #f87171; }}
                    .player-name {{ font-size: 13px; font-weight: 500; display: block; line-height: 1.4; }}
                    .score-winner {{ color: #4ade80; font-weight: 700; font-size: 15px; }}
                    .score-loser {{ color: #f87171; font-weight: 700; font-size: 15px; }}
                    .footer {{ text-align: center; margin-top: 24px; padding-top: 20px; border-top: 1px solid rgba(255, 255, 255, 0.08); }}
                    .link-button {{ display: inline-block; background-color: #66d9ef; color: #0b0f14; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px; }}
                    .opt-in-section {{ margin-top: 16px; padding-top: 16px; border-top: 1px solid rgba(255, 255, 255, 0.05); }}
                    .opt-in-text {{ color: #8b949e; font-size: 13px; margin-bottom: 10px; }}
                    .opt-in-button {{ display: inline-block; background-color: rgba(102, 217, 239, 0.15); color: #66d9ef; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 500; font-size: 13px; border: 1px solid rgba(102, 217, 239, 0.3); }}
                    .game-label {{ font-size: 11px; color: #8b949e; font-style: italic; }}
                    {hero_styles}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Game Recap{title_suffix} - {formatted_date}</h1>
                    {hero_block}
                    
                    <div class="card">
                        <h2>AI Summary</h2>
                        <div class="summary-text">
                            {summary_html}
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2>Player Stats</h2>
                        <table class="stats-table">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>Player</th>
                                    <th>W</th>
                                    <th>L</th>
                                    <th>Win %</th>
                                </tr>
                            </thead>
                            <tbody>
            """

    for index, stat in enumerate(stats, start=1):
        player_name = stat[0]
        wins = stat[1]
        losses = stat[2]
        win_pct = stat[3] * 100

        html_body += f"""
                                <tr>
                                    <td class="stats-rank">{index}</td>
                                    <td class="stats-player">{format_name_for_email(player_name)}</td>
                                    <td>{wins}</td>
                                    <td>{losses}</td>
                                    <td>{win_pct:.0f}%</td>
                                </tr>
                """

    html_body += """
                            </tbody>
                        </table>
                    </div>
                    
                    <div class="card">
                        <h2>Games (""" + str(len(games)) + """)</h2>
                        <table class="games-table">
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Game</th>
                                    <th>Winners</th>
                                    <th></th>
                                    <th>Losers</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
            """

    for game in games:
        time_display = ""
        game_date = game.get('game_date', '')
        if game_date:
            parts = str(game_date).strip().split()
            if len(parts) > 1:
                time_display = " ".join(parts[1:]).strip()
            elif parts:
                time_display = parts[0]
        if not time_display:
            time_display = "-"

        game_name = game.get('game_name', '')
        winners = game.get('winners', [])
        losers = game.get('losers', [])
        winner_names = "<br>".join(format_name_for_email(w['name']) for w in winners if w.get('name'))
        loser_names = "<br>".join(format_name_for_email(l['name']) for l in losers if l.get('name'))
        w_score = game.get('winner_score') or ''
        l_score = game.get('loser_score') or ''

        html_body += f"""
                                <tr>
                                    <td class="time-cell">{time_display}</td>
                                    <td class="game-label">{game_name}</td>
                                    <td class="winner-team">{winner_names}</td>
                                    <td class="score-winner">{w_score}</td>
                                    <td class="loser-team">{loser_names}</td>
                                    <td class="score-loser">{l_score}</td>
                                </tr>
                """

    stats_year = date_obj.year
    html_body += f"""
                            </tbody>
                        </table>
                    </div>
                    <div class="footer">
                        <a href="https://idynkydnk.pythonanywhere.com/other_stats/{stats_year}/" class="link-button">View {stats_year} Other Stats</a>
                        <div class="opt-in-section">
                            <p class="opt-in-text">Want all future AI summaries?</p>
                            <a href="https://idynkydnk.pythonanywhere.com/opt_in_ai_emails?email={{{{EMAIL_PLACEHOLDER}}}}" class="opt-in-button">Yes, include me</a>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """

    return html_body


def build_vollis_email_payload(selected_game_ids, prompt_style='announcer', custom_prompt=''):
    from vollis_functions import convert_vollis_ampm
    from player_functions import get_player_by_name

    PROMPT_STYLES = {
        'announcer': """You are an energetic sports announcer writing an exciting recap email.
Use dramatic language, exciting calls, and hype up big plays and close games.
Write like you're doing live ESPN commentary - high energy, dramatic pauses, and memorable catchphrases.
Make readers feel the excitement of being there. Use short punchy sentences mixed with longer dramatic buildups.
Keep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only. No long blocks of text.""",

        'analyst': """You are a data-driven sports analyst writing a statistical breakdown email.
Focus on the numbers: win percentages, point differentials, streaks, and trends.
Draw insights from the statistics and explain what they mean for each player's performance.
Be precise and factual, but still engaging. Reference specific stats to back up your observations.
Keep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only. No long blocks of text.""",

        'storyteller': """You are a sports storyteller writing a narrative recap email.
Weave the games into an engaging story with character development and dramatic tension.
Create narrative arcs - underdogs rising, champions defending, rivalries intensifying.
Use vivid imagery and build suspense. Make readers feel emotionally invested in the outcomes.
Keep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only. No long blocks of text.""",

        'comedian': """You are a comedy writer doing a sports recap email.
Be playful, witty, and don't be afraid to gently roast players (in good fun).
Find the humor in the games - funny moments, ironic outcomes, playful observations.
Keep it lighthearted and fun. Everyone should laugh, including those being teased.
Keep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only. No long blocks of text.""",

        'roast': """You are a brutal roast comedian writing a savage recap email.
Show absolutely NO mercy. Destroy everyone's performance with brutal honesty and savage insults.
Mock the winners for barely winning, demolish the losers for their failures.
Be creative with your insults - reference specific plays, scores, and failures.
This is all in good fun but don't hold back. Make it hurt (but funny).
Keep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only. No long blocks of text.""",
    }

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError('Gemini API key not configured.')

    if not current_app.config['MAIL_USERNAME'] or not current_app.config['MAIL_PASSWORD']:
        raise ValueError('Email not configured.')

    if not selected_game_ids:
        raise ValueError('No games selected.')

    from database_functions import create_connection
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        conn = create_connection('stats.db')
    cur = conn.cursor()
    placeholders = ','.join('?' * len(selected_game_ids))
    cur.execute(f"SELECT * FROM vollis_games WHERE id IN ({placeholders}) ORDER BY game_date DESC",
                [int(gid) for gid in selected_game_ids])
    raw_games = cur.fetchall()

    if not raw_games:
        raise ValueError('None of the selected games were found.')

    games = convert_vollis_ampm(raw_games)

    # Calculate simple stats from selected vollis games
    player_stats = {}
    for game in games:
        winner, loser = game[2], game[4]
        for name in [winner, loser]:
            if name and name.strip():
                if name not in player_stats:
                    player_stats[name] = {'wins': 0, 'losses': 0}
        if winner and winner.strip():
            player_stats[winner]['wins'] += 1
        if loser and loser.strip():
            player_stats[loser]['losses'] += 1

    stats = []
    for name, s in player_stats.items():
        total = s['wins'] + s['losses']
        if total > 0:
            stats.append([name, s['wins'], s['losses'], s['wins'] / total])
    stats.sort(key=lambda x: x[3], reverse=True)

    game_dates = sorted(set(str(game[1]).split(' ')[0] for game in games))
    if len(game_dates) == 1:
        date_str = game_dates[0]
    else:
        date_str = f"{game_dates[0]} to {game_dates[-1]}"

    context = f"Game Type: Vollis (1v1)\nDate: {date_str}\nTotal Games: {len(games)}\n\n"
    context += "Player Stats:\n"
    for stat in stats[:10]:
        win_pct = stat[3] * 100
        context += f"- {stat[0]}: {stat[1]}-{stat[2]} ({win_pct:.1f}%)\n"

    context += "\nGames Played (in chronological order):\n"
    for game in reversed(games[:10]):
        winner = game[2]
        loser = game[4]
        w_score = game[3]
        l_score = game[5]
        context += f"- {winner} def. {loser} ({w_score}-{l_score})\n"

    if prompt_style == 'custom' and custom_prompt.strip():
        style_instructions = custom_prompt.strip() + "\nKeep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only."
    else:
        style_instructions = PROMPT_STYLES.get(prompt_style, PROMPT_STYLES['announcer'])

    prompt = f"""{style_instructions}

Write in clean, professional sentences—no bullet points, asterisks, emojis, or decorative quotation marks.
Only quote a comment if it is already in the data enclosed in quotation marks.
Weave any comments smoothly into the narrative.
CRITICAL: Keep each paragraph to 2-3 sentences. Aim for under 100 words total. Be concise—readers will skim, not read long text.

Here is the game data:

{context}

Write the recap:"""
    summary = generate_ai_text(prompt)

    players_set = set()
    for game in games:
        for player_name in [game[2], game[4]]:
            if player_name and player_name.strip():
                players_set.add(player_name)

    players = []
    players_without_email = []
    for player_name in players_set:
        player_info = get_player_by_name(player_name)
        if player_info and player_info[2]:
            players.append({'name': player_name, 'email': player_info[2]})
        else:
            players_without_email.append(player_name)

    all_emails = [player['email'] for player in players]

    cur2 = conn.cursor()
    cur2.execute("SELECT email FROM players WHERE email IS NOT NULL AND notes LIKE ?", ('%AI_EMAILS_OPT_IN%',))
    opted_in_players = cur2.fetchall()
    for opt_in_player in opted_in_players:
        opt_in_email = opt_in_player[0]
        if opt_in_email and opt_in_email not in all_emails:
            all_emails.append(opt_in_email)

    date_values = [r[1] for r in raw_games if len(r) > 1 and r[1]]
    earliest_game_date = min(date_values) if date_values else datetime.now().strftime('%Y-%m-%d')
    try:
        date_obj = datetime.strptime(str(earliest_game_date)[:10], '%Y-%m-%d')
    except ValueError:
        try:
            date_obj = datetime.strptime(str(earliest_game_date)[:10], '%m/%d/%Y')
        except ValueError:
            date_obj = datetime.now()
    formatted_date = date_obj.strftime('%m/%d/%y')

    hero_image_url, hero_image_error = _try_generate_email_hero_image(
        api_key, 'vollis', games, summary, players_set,
    )
    html_body = create_vollis_email_html(
        summary, stats, games, date_obj, hero_image_url=hero_image_url,
    )
    subject = f"Vollis Summary - {formatted_date}"

    summary_preview = summary[:150] + "..." if len(summary) > 150 else summary

    return {
        'date': date_str,
        'games': games,
        'stats': stats,
        'summary': summary,
        'summary_preview': summary_preview,
        'context': context,
        'players': players,
        'players_without_email': players_without_email,
        'all_emails': all_emails,
        'html_body': html_body,
        'subject': subject,
        'hero_image_url': hero_image_url,
        'hero_image_error': hero_image_error,
        'date_obj': date_obj,
        'formatted_date': formatted_date
    }


def build_other_email_payload(selected_game_ids, prompt_style='announcer', custom_prompt=''):
    from other_functions import readable_games_data, _is_valid_player_name
    from player_functions import get_player_by_name

    PROMPT_STYLES = {
        'announcer': """You are an energetic sports announcer writing an exciting recap email.
Use dramatic language, exciting calls, and hype up big plays and close games.
Write like you're doing live ESPN commentary - high energy, dramatic pauses, and memorable catchphrases.
Make readers feel the excitement of being there. Use short punchy sentences mixed with longer dramatic buildups.
Keep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only. No long blocks of text.""",

        'analyst': """You are a data-driven sports analyst writing a statistical breakdown email.
Focus on the numbers: win percentages, point differentials, streaks, and trends.
Draw insights from the statistics and explain what they mean for each player's performance.
Be precise and factual, but still engaging. Reference specific stats to back up your observations.
Keep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only. No long blocks of text.""",

        'storyteller': """You are a sports storyteller writing a narrative recap email.
Weave the games into an engaging story with character development and dramatic tension.
Create narrative arcs - underdogs rising, champions defending, rivalries intensifying.
Use vivid imagery and build suspense. Make readers feel emotionally invested in the outcomes.
Keep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only. No long blocks of text.""",

        'comedian': """You are a comedy writer doing a sports recap email.
Be playful, witty, and don't be afraid to gently roast players (in good fun).
Find the humor in the games - funny moments, ironic outcomes, playful observations.
Keep it lighthearted and fun. Everyone should laugh, including those being teased.
Keep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only. No long blocks of text.""",

        'roast': """You are a brutal roast comedian writing a savage recap email.
Show absolutely NO mercy. Destroy everyone's performance with brutal honesty and savage insults.
Mock the winners for barely winning, demolish the losers for their failures.
Be creative with your insults - reference specific plays, scores, and failures.
This is all in good fun but don't hold back. Make it hurt (but funny).
Keep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only. No long blocks of text.""",
    }

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError('Gemini API key not configured.')

    if not current_app.config['MAIL_USERNAME'] or not current_app.config['MAIL_PASSWORD']:
        raise ValueError('Email not configured.')

    if not selected_game_ids:
        raise ValueError('No games selected.')

    import sqlite3
    from database_functions import create_connection
    database = '/home/Idynkydnk/stats/stats.db'
    conn = create_connection(database)
    if conn is None:
        conn = create_connection('stats.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    placeholders = ','.join('?' * len(selected_game_ids))
    cur.execute(f"SELECT * FROM other_games WHERE id IN ({placeholders}) ORDER BY game_date DESC",
                [int(gid) for gid in selected_game_ids])
    raw_games = cur.fetchall()

    if not raw_games:
        raise ValueError('None of the selected games were found.')

    games = readable_games_data(raw_games)

    # Calculate stats from the selected games
    player_stats = {}
    for game in games:
        for w in game.get('winners', []):
            name = w.get('name', '')
            if name and _is_valid_player_name(name):
                if name not in player_stats:
                    player_stats[name] = {'wins': 0, 'losses': 0}
                player_stats[name]['wins'] += 1
        for l in game.get('losers', []):
            name = l.get('name', '')
            if name and _is_valid_player_name(name):
                if name not in player_stats:
                    player_stats[name] = {'wins': 0, 'losses': 0}
                player_stats[name]['losses'] += 1

    stats = []
    for name, s in player_stats.items():
        total = s['wins'] + s['losses']
        if total > 0:
            stats.append([name, s['wins'], s['losses'], s['wins'] / total])
    stats.sort(key=lambda x: x[3], reverse=True)

    game_dates = sorted(set(str(game.get('game_date', '')).split(' ')[0] for game in games if game.get('game_date')))
    if len(game_dates) == 1:
        date_str = game_dates[0]
    else:
        date_str = f"{game_dates[0]} to {game_dates[-1]}"

    game_names = set(game.get('game_name', '') for game in games if game.get('game_name'))
    game_name_label = ', '.join(sorted(game_names)) if game_names else 'Other'

    context = f"Game Type: {game_name_label}\nDate: {date_str}\nTotal Games: {len(games)}\n\n"
    context += "Player Stats:\n"
    for stat in stats[:10]:
        win_pct = stat[3] * 100
        context += f"- {stat[0]}: {stat[1]}-{stat[2]} ({win_pct:.1f}%)\n"

    context += "\nGames Played (in chronological order):\n"
    for game in reversed(games[:10]):
        winner_names = ' & '.join(w['name'] for w in game.get('winners', []) if w.get('name'))
        loser_names = ' & '.join(l['name'] for l in game.get('losers', []) if l.get('name'))
        w_score = game.get('winner_score', '')
        l_score = game.get('loser_score', '')
        score_str = f" ({w_score}-{l_score})" if w_score and l_score else ""
        gn = game.get('game_name', '')
        game_label = f" [{gn}]" if gn else ""
        comment = game.get('comment', '')
        comment_str = f" - Comment: {comment}" if comment else ""
        context += f"- {winner_names} def. {loser_names}{score_str}{game_label}{comment_str}\n"

    if prompt_style == 'custom' and custom_prompt.strip():
        style_instructions = custom_prompt.strip() + "\nKeep it to 1-2 short paragraphs. Each paragraph: 2-3 sentences only."
    else:
        style_instructions = PROMPT_STYLES.get(prompt_style, PROMPT_STYLES['announcer'])

    prompt = f"""{style_instructions}

Write in clean, professional sentences—no bullet points, asterisks, emojis, or decorative quotation marks.
Only quote a comment if it is already in the data enclosed in quotation marks.
Weave any comments smoothly into the narrative.
CRITICAL: Keep each paragraph to 2-3 sentences. Aim for under 100 words total. Be concise—readers will skim, not read long text.

Here is the game data:

{context}

Write the recap:"""
    summary = generate_ai_text(prompt)

    players_set = set()
    for game in games:
        for w in game.get('winners', []):
            name = w.get('name', '')
            if name and _is_valid_player_name(name):
                players_set.add(name)
        for l in game.get('losers', []):
            name = l.get('name', '')
            if name and _is_valid_player_name(name):
                players_set.add(name)

    players = []
    players_without_email = []
    for player_name in players_set:
        player_info = get_player_by_name(player_name)
        if player_info and player_info[2]:
            players.append({'name': player_name, 'email': player_info[2]})
        else:
            players_without_email.append(player_name)

    all_emails = [player['email'] for player in players]

    conn2 = create_connection(database)
    if conn2 is None:
        conn2 = create_connection('stats.db')
    cur2 = conn2.cursor()
    cur2.execute("SELECT email FROM players WHERE email IS NOT NULL AND notes LIKE ?", ('%AI_EMAILS_OPT_IN%',))
    opted_in_players = cur2.fetchall()
    for opt_in_player in opted_in_players:
        opt_in_email = opt_in_player[0]
        if opt_in_email and opt_in_email not in all_emails:
            all_emails.append(opt_in_email)

    date_values = [dict(r).get('game_date') for r in raw_games if dict(r).get('game_date')]
    earliest_game_date = min(date_values) if date_values else datetime.now().strftime('%Y-%m-%d')
    try:
        date_obj = datetime.strptime(str(earliest_game_date)[:10], '%Y-%m-%d')
    except ValueError:
        try:
            date_obj = datetime.strptime(str(earliest_game_date)[:10], '%m/%d/%Y')
        except ValueError:
            date_obj = datetime.now()
    formatted_date = date_obj.strftime('%m/%d/%y')

    hero_image_url, hero_image_error = _try_generate_email_hero_image(
        api_key, 'other', games, summary, players_set,
    )
    html_body = create_other_email_html(
        summary, stats, games, date_obj, game_name_label,
        hero_image_url=hero_image_url,
    )
    subject = f"{game_name_label} Summary - {formatted_date}"

    summary_preview = summary[:150] + "..." if len(summary) > 150 else summary

    return {
        'date': date_str,
        'games': games,
        'stats': stats,
        'summary': summary,
        'summary_preview': summary_preview,
        'context': context,
        'players': players,
        'players_without_email': players_without_email,
        'all_emails': all_emails,
        'html_body': html_body,
        'subject': subject,
        'hero_image_url': hero_image_url,
        'hero_image_error': hero_image_error,
        'date_obj': date_obj,
        'formatted_date': formatted_date
    }
