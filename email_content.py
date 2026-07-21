"""HTML email bodies and AI summary payload builders for doubles, vollis, and other games.

Extracted from stats.py. These are pure content builders: they read games from the
database, call Gemini for the summary text, and return HTML/payload dicts. Sending
the email (Flask-Mail) stays in stats.py.
"""
import os
import html
import base64
import uuid
from datetime import datetime
from urllib.parse import quote

from flask import current_app

from other_functions import set_cur

SITE_BASE_URL = os.environ.get('SITE_BASE_URL', 'https://idynkydnk.pythonanywhere.com')
EMAIL_PLACEHOLDER = '{{EMAIL_PLACEHOLDER}}'
HERO_IMAGE_CID = 'hero-image'

# Free-tier image model for AI email illustrations.
GEMINI_IMAGE_MODEL = 'gemini-2.5-flash-image'

SOLO_BODY_PHOTOS_PER_PLAYER = 1

# Temporary solo caricatures (creator preview only). Prefix makes them easy to
# find and expire; group hero images keep the bare uuid filename.
SOLO_IMAGE_PREFIX = 'solo_'
SOLO_IMAGE_MAX_AGE_HOURS = 48

# WhatsApp requires og:image under 600KB; AI hero PNGs are often multi-MB.
OG_IMAGE_PREFIX = 'og_'
OG_IMAGE_MAX_BYTES = 500 * 1024
OG_IMAGE_MAX_WIDTH = 1200

IMAGE_MODES = ('none', 'image')
DEFAULT_IMAGE_MODE = 'none'
_LEGACY_IMAGE_MODES = {'single': 'image', 'two_pass': 'image'}


class ImageGenerationError(Exception):
    """Image API failed after the illustration prompt was assembled."""

    def __init__(self, message, image_prompt=None, solo_images=None):
        super().__init__(message)
        self.image_prompt = image_prompt or ''
        self.solo_images = solo_images or []


def _normalize_image_mode(mode):
    clean = (mode or '').strip().lower()
    if clean in IMAGE_MODES:
        return clean
    if clean in _LEGACY_IMAGE_MODES:
        return _LEGACY_IMAGE_MODES[clean]
    return DEFAULT_IMAGE_MODE


def image_mode_label(mode):
    labels = {
        'none': 'text only',
        'image': 'with illustration',
    }
    return labels.get(_normalize_image_mode(mode), labels[DEFAULT_IMAGE_MODE])


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


RECAP_PARAGRAPH_LIMIT = (
    'Keep it to 2 short paragraphs. Each paragraph: 2-3 sentences only. '
    'No long blocks of text. talk about any notable stats'
)

DEFAULT_RECAP_STYLE_INSTRUCTIONS = (
    'Write a clear, factual game recap using only the information provided below. '
    'Cover what happened: results, scores, notable stats, and standout moments from the data. '
    'Use a natural, readable tone. Do not invent a persona, gimmick, fictional framing, '
    'or details that are not in the data.'
)

_LEGACY_PROMPT_STYLE_ALIASES = {
    'random': 'default',
    'generated_1': 'default',
    'generated_2': 'default',
    'brutal': 'default',
    'roast': 'default',
    'announcer': 'default',
    'analyst': 'default',
    'storyteller': 'default',
    'comedian': 'default',
    'funny': 'default',
    'ai': 'default',
}


def _normalize_prompt_style(prompt_style):
    clean = (prompt_style or '').strip().lower()
    return _LEGACY_PROMPT_STYLE_ALIASES.get(clean, clean or 'default')


def _strip_recap_paragraph_limit(text):
    """Remove the appended length constraint so the user can edit the style cleanly."""
    clean = (text or '').strip()
    limit = RECAP_PARAGRAPH_LIMIT.strip()
    if clean.endswith(limit):
        clean = clean[: -len(limit)].rstrip()
    return clean


def _build_recap_style_instructions(prompt_style, context, custom_prompt=''):
    """Resolve writing-style instructions for a recap (default factual, or custom)."""
    prompt_style = _normalize_prompt_style(prompt_style)

    if prompt_style == 'custom':
        if not custom_prompt.strip():
            raise ValueError('Custom prompt is empty. Enter your style instructions first.')
        return custom_prompt.strip() + f'\n{RECAP_PARAGRAPH_LIMIT}'

    if prompt_style == 'default':
        return f'{DEFAULT_RECAP_STYLE_INSTRUCTIONS}\n{RECAP_PARAGRAPH_LIMIT}'

    raise ValueError(f'Unknown prompt style: {prompt_style}')


def _build_recap_prompt(style_instructions, context):
    return f"""{style_instructions}

Write in clean, professional sentences—no bullet points, asterisks, emojis, or decorative quotation marks.
If any games include comments, you must weave every comment into the summary. Do not skip or ignore comments.
Only quote a comment if it is already in the data enclosed in quotation marks.
Base the recap only on the information below.

{context}"""


def _email_hero_styles():
    return """
                    .hero-image-card { padding: 0; text-align: center; }
                    .hero-image-card img { width: 100%; max-width: 600px; height: auto; display: block; border-radius: 12px; }
    """


def _email_games_table_styles():
    return """
                    .games-table-wrap {
                        overflow-x: auto;
                        -webkit-overflow-scrolling: touch;
                        max-width: 100%;
                    }
                    .games-table {
                        width: 100%;
                        border-collapse: collapse;
                        color: #e4e8eb;
                        font-size: 13px;
                        table-layout: fixed;
                    }
                    .games-table thead {
                        background: rgba(255, 255, 255, 0.03);
                    }
                    .games-table th {
                        padding: 10px 4px;
                        text-align: center;
                        font-size: 10px;
                        font-weight: 600;
                        text-transform: uppercase;
                        letter-spacing: 0.4px;
                        color: #8b949e;
                    }
                    .games-table td {
                        padding: 10px 4px;
                        text-align: center;
                        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                        vertical-align: middle;
                    }
                    .games-table tbody tr:last-child td {
                        border-bottom: none;
                    }
                    .games-table tbody tr:nth-child(odd) {
                        background: rgba(255, 255, 255, 0.02);
                    }
                    .time-cell {
                        font-size: 11px;
                        color: #8b949e;
                        text-align: left;
                        padding-right: 6px;
                        line-height: 1.35;
                        word-break: break-word;
                    }
                    .team-cell {
                        text-align: left;
                        overflow-wrap: anywhere;
                        word-break: break-word;
                    }
                    .winner-team {
                        color: #4ade80;
                    }
                    .loser-team {
                        color: #f87171;
                    }
                    .player-name {
                        font-size: 12px;
                        font-weight: 500;
                        display: block;
                        line-height: 1.35;
                        overflow-wrap: anywhere;
                        word-break: break-word;
                        text-decoration: none;
                        color: inherit;
                    }
                    a.player-name:link,
                    a.player-name:visited,
                    a.player-name:hover,
                    a.player-name:active {
                        text-decoration: none;
                        color: inherit;
                    }
                    .score-winner {
                        color: #4ade80;
                        font-weight: 700;
                        font-size: 14px;
                        white-space: nowrap;
                        padding-left: 4px;
                    }
                    .score-loser {
                        color: #f87171;
                        font-weight: 700;
                        font-size: 14px;
                        white-space: nowrap;
                        padding-left: 4px;
                    }
                    @media (max-width: 480px) {
                        body { padding: 12px; }
                        .card { padding: 12px; }
                        .games-table { font-size: 12px; }
                        .games-table th { font-size: 9px; padding: 8px 2px; }
                        .games-table td { padding: 8px 2px; }
                        .player-name { font-size: 11px; }
                        .time-cell { font-size: 10px; }
                        .score-winner, .score-loser { font-size: 13px; }
                    }
    """


def _email_hero_html(hero_image_url, use_cid=False):
    if not hero_image_url and not use_cid:
        return ''
    src = f'cid:{HERO_IMAGE_CID}' if use_cid else hero_image_url
    img_style = (
        'display:block;width:100%;max-width:600px;height:auto;border:0;'
        'border-radius:12px;margin:0 auto;'
    )
    return f"""
                    <div class="card hero-image-card">
                        <img src="{src}" alt="AI game illustration" width="600" border="0"
                             style="{img_style}">
                    </div>
    """


def replace_recap_hero_image(html_body, new_hero_url):
    """Replace or insert the hero illustration block in published recap HTML."""
    from bs4 import BeautifulSoup

    if not html_body or not str(html_body).strip():
        return html_body or ''

    soup = BeautifulSoup(html_body, 'html.parser')
    hero_card = soup.select_one('.hero-image-card')
    new_url = (new_hero_url or '').strip()

    if not new_url:
        if hero_card:
            hero_card.decompose()
        return str(soup)

    # Ensure hero CSS exists in a style tag.
    hero_css = (
        '.hero-image-card { padding: 0; text-align: center; }'
        '.hero-image-card img { width: 100%; max-width: 600px; height: auto; '
        'display: block; border-radius: 12px; }'
    )
    style_tag = soup.find('style')
    if style_tag:
        style_text = style_tag.string or style_tag.get_text() or ''
        if 'hero-image-card' not in style_text:
            style_tag.string = style_text + hero_css
    else:
        head = soup.find('head')
        if head:
            new_style = soup.new_tag('style')
            new_style.string = hero_css
            head.append(new_style)

    img_style = (
        'display:block;width:100%;max-width:600px;height:auto;border:0;'
        'border-radius:12px;margin:0 auto;'
    )
    if hero_card:
        img = hero_card.find('img')
        if img:
            img['src'] = new_url
        else:
            hero_card.clear()
            img = soup.new_tag(
                'img',
                src=new_url,
                alt='AI game illustration',
                width='600',
                border='0',
                style=img_style,
            )
            hero_card.append(img)
        return str(soup)

    # Insert a new hero card after the title when the recap was text-only.
    card = soup.new_tag('div', **{'class': 'card hero-image-card'})
    img = soup.new_tag(
        'img',
        src=new_url,
        alt='AI game illustration',
        width='600',
        border='0',
        style=img_style,
    )
    card.append(img)
    container = soup.select_one('.container') or soup.find('body') or soup
    title = container.find('h1') if container else None
    if title:
        title.insert_after(card)
    elif container:
        if container.contents:
            container.insert(0, card)
        else:
            container.append(card)
    else:
        soup.insert(0, card)
    return str(soup)


def ai_email_subject(game_type, date_obj, game_name_label=''):
    """Human-friendly subject line for better inbox placement."""
    date_label = date_obj.strftime('%b ') + str(date_obj.day)
    if game_type == 'doubles':
        return f'Volleyball recap – {date_label} (your group)'
    if game_type == 'vollis':
        return f'Vollis recap – {date_label} (your group)'
    label = (game_name_label or 'Game').strip()
    return f'{label} recap – {date_label} (your group)'


def _sanitize_email_subject(raw):
    """Clean AI subject output to a single short line."""
    if not raw:
        return ''
    subject = raw.strip().splitlines()[0].strip()
    for prefix in ('Subject line:', 'Subject:', 'subject:'):
        if subject.lower().startswith(prefix.lower()):
            subject = subject[len(prefix):].strip()
    if len(subject) >= 2 and subject[0] == subject[-1] and subject[0] in '"\'':
        subject = subject[1:-1].strip()
    return subject[:60].strip()


def generate_ai_email_subject(summary, game_type, date_obj, game_name_label=''):
    """Generate a short subject from the recap. Falls back to a template."""
    fallback = ai_email_subject(game_type, date_obj, game_name_label)
    if not (summary or '').strip():
        return fallback

    date_label = date_obj.strftime('%b ') + str(date_obj.day)
    if game_type == 'doubles':
        game_label = 'volleyball'
    elif game_type == 'vollis':
        game_label = 'vollis'
    else:
        game_label = (game_name_label or 'game').strip().lower()

    prompt = f"""Write one short email subject line for this {game_label} recap from {date_label}.

Rules:
- Max 50 characters (hard limit)
- Punchy and specific to what happened—not generic like "recap"
- No quotes, emojis, or "Subject:" prefix
- Output only the subject line, nothing else

Recap:
{summary.strip()[:500]}"""

    try:
        subject = _sanitize_email_subject(generate_ai_text(prompt))
        if subject and len(subject) <= 60:
            return subject
    except Exception:
        pass
    return fallback


def personalize_ai_email_content(html_body, plain_text_body, recipient_email, hero_image_url=None, embed_hero=False):
    """Per-recipient HTML/plain text with encoded opt-in/unsubscribe links."""
    from urllib.parse import quote

    email_param = quote(recipient_email.strip(), safe='')
    replacements = {EMAIL_PLACEHOLDER: email_param}
    html = html_body or ''
    text = plain_text_body or ''
    for old, new in replacements.items():
        html = html.replace(old, new)
        text = text.replace(old, new)
    if embed_hero and hero_image_url and html:
        html = html.replace(hero_image_url, f'cid:{HERO_IMAGE_CID}')
    return html, text


def plain_text_fallback_from_html(html_body):
    """Best-effort plain text when only HTML is available (legacy preview sends)."""
    from bs4 import BeautifulSoup

    if not html_body or not str(html_body).strip():
        return ''
    soup = BeautifulSoup(html_body, 'html.parser')
    for tag in soup(['style', 'script']):
        tag.decompose()
    text = soup.get_text('\n')
    lines = [line.strip() for line in text.splitlines()]
    return '\n'.join(line for line in lines if line)


def _ordered_email_image_players(player_names):
    """Unique, stable player list for email illustrations (alphabetical)."""
    seen = set()
    ordered = []
    for name in sorted(player_names or [], key=lambda n: (n or '').strip().lower()):
        clean = (name or '').strip()
        key = clean.lower()
        if not clean or key in seen:
            continue
        seen.add(key)
        ordered.append(clean)
    return ordered


def _dedupe_players_preserve_order(player_names):
    """Unique player list preserving input order."""
    seen = set()
    ordered = []
    for name in player_names or []:
        clean = (name or '').strip()
        key = clean.lower()
        if not clean or key in seen:
            continue
        seen.add(key)
        ordered.append(clean)
    return ordered


def resolve_illustration_players(player_names, selected_players=None):
    """Return the full roster for illustrations.

    Players without a face photo or signature looks are skipped later during
    generation. selected_players is ignored; kept for call-site compatibility.
    """
    return _ordered_email_image_players(player_names)


def _illustration_players(player_names, game_type, games, selected_players=None):
    """Choose roster for illustration. Always two-pass: solo caricatures, then group."""
    all_players = _ordered_email_image_players(player_names)
    if not all_players:
        return [], 'two_pass', all_players
    return list(all_players), 'two_pass', all_players


def _solo_reference_parts_for_player(name, entry):
    """Build face-reference parts for a solo caricature call."""
    parts = [{'text': '=== Character reference ==='}]
    if not entry or not entry.get('parts'):
        parts.append({
            'text': (
                'No face reference photo. Invent one unique stylized character '
                'from the signature details in the prompt below.'
            ),
        })
        return parts

    for ref in entry['parts']:
        parts.append({'text': 'Face reference. Use for facial features and expression.'})
        parts.append({'inline_data': {'mime_type': ref['mime'], 'data': ref['data_b64']}})
    return parts


def _player_can_illustrate(has_reference_photos, trait_phrases):
    """Only illustrate players who have a face photo and/or signature looks."""
    return bool(has_reference_photos) or bool(trait_phrases)


def _build_solo_player_prompt(name, trait_phrases, has_reference_photos):
    traits_block = ''
    if trait_phrases:
        traits_block = (
            '\nSignature exaggerations:\n'
            + '\n'.join(f'- {phrase}' for phrase in trait_phrases)
            + '\n'
        )
    if has_reference_photos:
        likeness = (
            'Use the attached face reference photo to capture this person\'s face, '
            'then exaggerate their signature details so they are instantly recognizable.\n'
        )
    else:
        likeness = (
            'invent a unique character from the signature details below.\n'
        )
    return f"""Draw exactly ONE person.
{likeness}{traits_block}
Plain neutral background."""


def build_flyer_solo_prompt(player_name):
    """Build the default flyer solo prompt (same as doubles AI recap individuals)."""
    return build_solo_caricature_prompt(player_name)


def build_flyer_scene_prompt(
    players, game_type, event_date='', event_time='', location='',
    game_name=None, image_details='',
):
    """Build the default Instagram flyer group prompt."""
    sport_desc = _sport_desc_for_image(game_type, game_name)
    roster_block, player_count, players = _image_roster_block(players)
    details_block = _image_details_block(image_details)
    when_bits = [bit for bit in [(event_date or '').strip(), (event_time or '').strip()] if bit]
    when_line = ' '.join(when_bits) if when_bits else 'TBD'
    where_line = (location or '').strip() or 'TBD'
    title = sport_desc.title() if sport_desc else 'Game Night'
    return f"""Create a bold promotional Instagram flyer for an upcoming game.
Event: {title}
When: {when_line}
Where: {where_line}
{details_block}{roster_block}
Use each attached character reference exactly — same face, hair, outfit per person.
Draw all {player_count} people in the scene — one per Person number.
Include clear, readable flyer text for the event title, date/time, and location.
Compose as a vertical 4:5 Instagram portrait (taller than wide). Keep every person
fully inside the frame with comfortable margin — no one cut off at the edges.
Energetic, fun, poster-quality illustration — not a plain photo collage."""


def _sport_desc_for_image(game_type, game_name=None):
    if game_type == 'doubles':
        return 'beach volleyball doubles'
    if game_type == 'vollis':
        return 'one-on-one vollis volleyball'
    if game_type == 'other' and game_name:
        return game_name
    return 'recreational games'


def _image_details_block(image_details):
    clean = (image_details or '').strip()
    if not clean:
        return ''
    return f'\n{clean}\n'


def _image_roster_block(players):
    """Simple numbered roster for the group scene."""
    players = _dedupe_players_preserve_order(players)
    player_count = len(players)
    if player_count == 0:
        return '', 0, players
    roster_lines = '\n'.join(
        f'{index}. Person {index}' for index in range(1, player_count + 1)
    )
    block = (
        f'\n{player_count} players (Person 1 through Person {player_count}):\n'
        f'{roster_lines}\n'
    )
    return block, player_count, players


def build_scene_image_prompt(game_type, players, game_name=None, image_details=''):
    """Build the default group-scene prompt (for preview/edit in the UI)."""
    sport_desc = _sport_desc_for_image(game_type, game_name)
    roster_block, player_count, players = _image_roster_block(players)
    details_block = _image_details_block(image_details)
    return f"""Game: {sport_desc}.
{details_block}{roster_block}
Use each attached character reference exactly — same face, hair, outfit per person.
Draw all {player_count} people in the scene — one per Person number.
Compose as a vertical 4:5 portrait (taller than wide). Keep every person fully inside the frame with comfortable margin — no one cut off at the edges."""


def _build_scene_image_prompt(game_type, players, game_name=None, image_details=''):
    return build_scene_image_prompt(
        game_type, players, game_name=game_name, image_details=image_details,
    )


def _reference_parts_from_caricatures(players, caricatures):
    """Attach pass-1 caricatures as numbered scene references."""
    roster_block, player_count, players = _image_roster_block(players)
    parts = [{
        'text': (
            f'{player_count} players, each with a caricature reference attached below.'
            f'{roster_block}'
        ),
    }]
    for index, name in enumerate(players, start=1):
        raw, mime = caricatures[name]
        parts.append({'text': f'Person {index} — use this caricature exactly:'})
        parts.append({
            'inline_data': {
                'mime_type': mime,
                'data': base64.b64encode(raw).decode('ascii'),
            },
        })
    return parts


def _is_quota_error(msg):
    s = str(msg).lower()
    return '429' in s or 'quota' in s or 'rate limit' in s or 'exceeded your current quota' in s


def _friendly_image_error(err, api_calls=1):
    if _is_quota_error(err):
        call_note = (
            f'each illustrated email uses {api_calls} image{"s" if api_calls != 1 else ""}'
        )
        return (
            'Daily free image quota is used up on the shared Gemini API key '
            f'(~500 images/day on gemini-2.5-flash-image; {call_note}). '
            'The text summary still works. Try again tomorrow, or enable billing in Google AI '
            'Studio for more image generation.'
        )
    return str(err)[:400]


def _rest_error_detail(resp):
    try:
        data = resp.json()
        return data.get('error', {}).get('message') or resp.text[:300]
    except Exception:
        return resp.text[:300] if resp.text else f'HTTP {resp.status_code}'


def _generate_image_bytes(prompt, api_key, reference_parts=None, aspect_ratio=None):
    """One API call to the free-tier Gemini image model."""
    import requests

    parts = list(reference_parts or [])
    parts.append({'text': prompt})

    headers = {'x-goog-api-key': api_key, 'Content-Type': 'application/json'}
    url = (
        f'https://generativelanguage.googleapis.com/v1beta/models/'
        f'{GEMINI_IMAGE_MODEL}:generateContent'
    )
    generation_config = {'responseModalities': ['IMAGE']}
    if aspect_ratio:
        generation_config['imageConfig'] = {'aspectRatio': aspect_ratio}
    payload = {
        'contents': [{'parts': parts}],
        'generationConfig': generation_config,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    if resp.status_code >= 400:
        raise ValueError(_rest_error_detail(resp))
    data = resp.json()
    pf = data.get('promptFeedback') or data.get('prompt_feedback') or {}
    block = pf.get('blockReason') or pf.get('block_reason')
    if block:
        raise ValueError(f'blocked ({block})')
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
    raise ValueError(f'no image in response (finish={fr})')


def _save_email_image(image_bytes, ext, prefix=''):
    base = os.path.dirname(os.path.abspath(__file__))
    dest_dir = os.path.join(base, 'static', 'email_images')
    os.makedirs(dest_dir, exist_ok=True)
    filename = f'{prefix}{uuid.uuid4().hex}.{ext}'
    abs_path = os.path.join(dest_dir, filename)
    with open(abs_path, 'wb') as f:
        f.write(image_bytes)
    url = f'{SITE_BASE_URL}/static/email_images/{filename}'
    return url, abs_path


def _normalize_image_bytes_to_aspect(image_bytes, ratio_w=4, ratio_h=5):
    """Center-crop/scale image bytes to an exact aspect ratio (default Instagram 4:5)."""
    import io
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    width, height = img.size
    if width < 2 or height < 2:
        return image_bytes, 'image/jpeg'
    target = ratio_w / float(ratio_h)
    current = width / float(height)
    if abs(current - target) < 0.01:
        out_w, out_h = width, height
    elif current > target:
        out_h = height
        out_w = max(1, int(round(height * target)))
    else:
        out_w = width
        out_h = max(1, int(round(width / target)))
    fitted = ImageOps.fit(img, (out_w, out_h), method=_pil_lanczos())
    buf = io.BytesIO()
    fitted.save(buf, format='JPEG', quality=92, optimize=True)
    return buf.getvalue(), 'image/jpeg'


def _email_image_path_from_url(image_url):
    """Resolve a /static/email_images/... URL to an absolute path if the file exists."""
    url = (image_url or '').strip()
    marker = '/static/email_images/'
    if marker not in url:
        return None
    filename = os.path.basename(url.split(marker, 1)[1].split('?', 1)[0])
    if not filename or filename.startswith('.') or '/' in filename or '\\' in filename:
        return None
    path = os.path.join(email_images_dir(), filename)
    return path if os.path.isfile(path) else None


def _pil_lanczos():
    from PIL import Image

    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS


def _jpeg_preview_under_limit(img, max_bytes=OG_IMAGE_MAX_BYTES, max_width=OG_IMAGE_MAX_WIDTH):
    """Encode a PIL image as JPEG under max_bytes for WhatsApp og:image."""
    import io
    from PIL import Image

    if img.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img.convert('RGBA'), mask=img.split()[-1])
        img = background
    elif img.mode == 'P':
        img = img.convert('RGBA').convert('RGB')
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    resample = _pil_lanczos()
    w, h = img.size
    if w > max_width:
        scale = max_width / float(w)
        img = img.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            resample,
        )

    best = None
    working = img
    for _ in range(8):
        for quality in (85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30):
            buf = io.BytesIO()
            working.save(buf, format='JPEG', quality=quality, optimize=True)
            data = buf.getvalue()
            if best is None or len(data) < len(best):
                best = data
            if len(data) <= max_bytes:
                return data, working.size
        ww, hh = working.size
        if max(ww, hh) <= 480:
            break
        working = working.resize(
            (max(1, ww // 2), max(1, hh // 2)),
            resample,
        )
    return best, (working.size if working is not None else img.size)


def _load_hero_image_bytes(hero_image_url):
    """Load hero image bytes from disk, or fall back to the public URL."""
    import urllib.request

    hero_path = _email_image_path_from_url(hero_image_url)
    if hero_path:
        with open(hero_path, 'rb') as handle:
            return handle.read(), hero_path

    url = (hero_image_url or '').strip()
    if url.startswith('/'):
        url = SITE_BASE_URL.rstrip('/') + url
    if not url.startswith('http://') and not url.startswith('https://'):
        raise FileNotFoundError(f'Hero image not found for {hero_image_url!r}')

    request = urllib.request.Request(
        url,
        headers={'User-Agent': 'StatsRecapOG/1.0'},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read(), None


def build_recap_og_jpeg(hero_image_url):
    """Return (jpeg_bytes, width, height, cache_path) for a WhatsApp-safe preview.

    Writes a cached og_*.jpg beside the hero when possible. Always returns
    in-memory JPEG bytes when the hero file can be read, even if disk cache fails.
    """
    import io
    from PIL import Image, ImageOps

    raw, hero_path = _load_hero_image_bytes(hero_image_url)
    if not raw:
        raise FileNotFoundError(f'Hero image empty for {hero_image_url!r}')

    marker = '/static/email_images/'
    if hero_path:
        filename = os.path.basename(hero_path)
    elif marker in (hero_image_url or ''):
        filename = os.path.basename(
            hero_image_url.split(marker, 1)[1].split('?', 1)[0]
        )
    else:
        filename = 'hero.png'

    stem = os.path.splitext(filename)[0] or 'hero'
    if stem.startswith(OG_IMAGE_PREFIX):
        with Image.open(io.BytesIO(raw)) as img:
            return raw, img.size[0], img.size[1], hero_path

    og_filename = f'{OG_IMAGE_PREFIX}{stem}.jpg'
    og_path = os.path.join(email_images_dir(), og_filename)

    if os.path.isfile(og_path) and 0 < os.path.getsize(og_path) <= OG_IMAGE_MAX_BYTES:
        with open(og_path, 'rb') as handle:
            data = handle.read()
        with Image.open(io.BytesIO(data)) as img:
            return data, img.size[0], img.size[1], og_path

    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img)
    data, (width, height) = _jpeg_preview_under_limit(img)
    if not data:
        raise ValueError('Failed to compress hero image for WhatsApp preview.')

    try:
        tmp_path = f'{og_path}.tmp'
        with open(tmp_path, 'wb') as handle:
            handle.write(data)
        os.replace(tmp_path, og_path)
        cache_path = og_path
    except OSError:
        cache_path = None

    return data, width, height, cache_path


def ensure_recap_og_image(hero_image_url):
    """Build a WhatsApp-safe JPEG preview for og:image.

    AI/uploaded heroes are often multi-MB PNGs; WhatsApp drops previews over 600KB.
    Returns {url, width, height, path} or empty dict when no usable preview exists.
    """
    if not (hero_image_url or '').strip():
        return {}
    try:
        data, width, height, cache_path = build_recap_og_jpeg(hero_image_url)
    except Exception as exc:
        try:
            from flask import current_app
            current_app.logger.exception(
                'Failed to build WhatsApp OG preview for %s: %s',
                hero_image_url, exc,
            )
        except Exception:
            pass
        return {}

    if cache_path and os.path.isfile(cache_path):
        url = f'{SITE_BASE_URL}/static/email_images/{os.path.basename(cache_path)}'
        return {
            'url': url,
            'width': width,
            'height': height,
            'path': cache_path,
            'bytes': data,
        }
    return {
        'url': '',
        'width': width,
        'height': height,
        'path': '',
        'bytes': data,
    }


def delete_recap_og_image_for_hero(hero_image_url):
    """Remove the WhatsApp OG preview file paired with a hero image, if present."""
    hero_path = _email_image_path_from_url(hero_image_url)
    if not hero_path:
        return False
    stem = os.path.splitext(os.path.basename(hero_path))[0]
    if stem.startswith(OG_IMAGE_PREFIX):
        return False
    og_path = os.path.join(email_images_dir(), f'{OG_IMAGE_PREFIX}{stem}.jpg')
    try:
        os.remove(og_path)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


# Instagram carousel slides: 4:5 portrait (1080×1350) — Instagram's preferred feed size.
IG_SLIDE_W = 1080
IG_SLIDE_H = 1350
# Bump when slide layout changes so cached JPEGs are rebuilt.
IG_SLIDE_VERSION = 4
IG_SLIDE_FILES = (
    ('1_photo.jpg', 'photo'),
    ('2_summary.jpg', 'summary'),
    ('3_stats.jpg', 'stats'),
    ('4_games.jpg', 'games'),
)
IG_BG = (11, 15, 20)
IG_PANEL = (19, 26, 36)
IG_LINE = (255, 255, 255, 20)
IG_TEXT = (228, 232, 235)
IG_MUTED = (139, 148, 158)
IG_ACCENT = (102, 217, 239)
IG_WIN = (74, 222, 128)
IG_LOSS = (248, 113, 113)


def instagram_slides_dir(share_id):
    """Directory for a recap's Instagram slide JPEGs."""
    safe_id = ''.join(ch for ch in (share_id or '') if ch.isalnum() or ch in ('-', '_'))
    if not safe_id:
        raise ValueError('Invalid recap id')
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'static', 'recaps', safe_id,
    )
    os.makedirs(path, exist_ok=True)
    return path


def delete_instagram_slides(share_id):
    """Remove generated Instagram slides for a recap, if any."""
    import shutil

    try:
        path = instagram_slides_dir(share_id)
    except ValueError:
        return False
    if not os.path.isdir(path):
        return False
    try:
        shutil.rmtree(path)
        return True
    except OSError:
        return False


def list_instagram_slide_paths(share_id):
    """Return ordered list of existing slide paths, or [] if incomplete/outdated."""
    from PIL import Image

    try:
        base = instagram_slides_dir(share_id)
    except ValueError:
        return []
    version_path = os.path.join(base, 'version.txt')
    try:
        with open(version_path, 'r', encoding='utf-8') as handle:
            version = int((handle.read() or '').strip() or '0')
    except (OSError, ValueError):
        version = 0
    if version != IG_SLIDE_VERSION:
        return []
    paths = []
    for filename, _kind in IG_SLIDE_FILES:
        path = os.path.join(base, filename)
        if not os.path.isfile(path) or os.path.getsize(path) <= 0:
            return []
        try:
            with Image.open(path) as img:
                if img.size != (IG_SLIDE_W, IG_SLIDE_H):
                    return []
        except OSError:
            return []
        paths.append(path)
    return paths


def _ig_load_font(size, bold=False):
    """Best-effort system font for Instagram slides (macOS + Linux)."""
    from PIL import ImageFont

    candidates = []
    if bold:
        candidates.extend([
            '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
            '/Library/Fonts/Arial Bold.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
            '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
        ])
    candidates.extend([
        '/System/Library/Fonts/Supplemental/Arial.ttf',
        '/Library/Fonts/Arial.ttf',
        '/System/Library/Fonts/Helvetica.ttc',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
    ])
    for path in candidates:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _ig_text_width(draw, text, font):
    if hasattr(draw, 'textlength'):
        try:
            return draw.textlength(text, font=font)
        except Exception:
            pass
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _ig_text_height(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[3] - box[1]


def _ig_summary_text_from_html(summary_el):
    """Extract summary plain text, preserving paragraph breaks from <br>/<p>."""
    from bs4 import BeautifulSoup

    if summary_el is None:
        return ''
    # Work on a copy so we don't mutate the parsed email tree.
    node = BeautifulSoup(str(summary_el), 'html.parser')
    root = node.select_one('.summary-text') or node
    for br in root.find_all('br'):
        br.replace_with('\n')
    for p in root.find_all('p'):
        p.insert_before('\n\n')
        p.insert_after('\n\n')
        p.unwrap()
    return root.get_text('', strip=False)


def _ig_normalize_summary_paragraphs(text):
    """Ensure summary has blank-line paragraph breaks for Instagram slides."""
    import re

    text = (text or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        return text
    lines = [ln.strip() for ln in text.split('\n')]
    text = '\n'.join(lines)
    while '\n\n\n' in text:
        text = text.replace('\n\n\n', '\n\n')
    text = text.strip()
    if '\n\n' in text:
        return text
    if '\n' in text:
        return '\n\n'.join(p for p in (part.strip() for part in text.split('\n')) if p)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) <= 2:
        return text
    n = len(sentences)
    if n <= 5:
        mid = (n + 1) // 2
        parts = [' '.join(sentences[:mid]), ' '.join(sentences[mid:])]
    else:
        a = max(1, n // 3)
        b = max(a + 1, (2 * n) // 3)
        parts = [
            ' '.join(sentences[:a]),
            ' '.join(sentences[a:b]),
            ' '.join(sentences[b:]),
        ]
    return '\n\n'.join(p for p in parts if p)


def _ig_wrap_text(draw, text, font, max_width):
    """Word-wrap text to fit max_width; returns list of lines."""
    text = (text or '').replace('\r\n', '\n').replace('\r', '\n')
    lines = []
    for paragraph in text.split('\n'):
        words = paragraph.split()
        if not words:
            lines.append('')
            continue
        current = words[0]
        for word in words[1:]:
            trial = f'{current} {word}'
            if _ig_text_width(draw, trial, font) <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _ig_fit_wrapped_lines(draw, text, max_width, max_height, size_start, size_min, bold=False, line_gap=1.28):
    """Shrink font until wrapped text fits in max_height. Returns (lines, font, line_h)."""
    for size in range(size_start, size_min - 1, -2):
        font = _ig_load_font(size, bold=bold)
        lines = _ig_wrap_text(draw, text, font, max_width)
        if not lines:
            return [], font, 0
        line_h = max(_ig_text_height(draw, 'Ag', font), size)
        total = int(len(lines) * line_h * line_gap)
        if total <= max_height:
            return lines, font, line_h
    font = _ig_load_font(size_min, bold=bold)
    lines = _ig_wrap_text(draw, text, font, max_width)
    line_h = max(_ig_text_height(draw, 'Ag', font), size_min)
    # Truncate with ellipsis if still too tall.
    max_lines = max(1, int(max_height / (line_h * line_gap)))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines:
            lines[-1] = lines[-1].rstrip('.…') + '…'
    return lines, font, line_h


def _ig_draw_header(draw, title, subtitle=''):
    """Accent eyebrow + title at top of a text slide."""
    pad = 72
    eyebrow_font = _ig_load_font(28, bold=True)
    title_font = _ig_load_font(52, bold=True)
    y = pad
    eyebrow = 'GAME RECAP'
    ew = _ig_text_width(draw, eyebrow, eyebrow_font)
    draw.text(((IG_SLIDE_W - ew) / 2, y), eyebrow, font=eyebrow_font, fill=IG_ACCENT)
    y += 44
    # Underline accent bar
    bar_w = 72
    draw.rectangle(
        [(IG_SLIDE_W - bar_w) // 2, y, (IG_SLIDE_W + bar_w) // 2, y + 4],
        fill=IG_ACCENT,
    )
    y += 28
    title_lines = _ig_wrap_text(draw, title or 'Recap', title_font, IG_SLIDE_W - pad * 2)
    for line in title_lines[:3]:
        tw = _ig_text_width(draw, line, title_font)
        draw.text(((IG_SLIDE_W - tw) / 2, y), line, font=title_font, fill=IG_TEXT)
        y += 60
    if subtitle:
        sub_font = _ig_load_font(30)
        sw = _ig_text_width(draw, subtitle, sub_font)
        draw.text(((IG_SLIDE_W - sw) / 2, y), subtitle, font=sub_font, fill=IG_MUTED)
        y += 48
    return y + 12


def parse_recap_for_instagram(html_body, plain_text_body='', subject='', hero_image_url=''):
    """Extract slide content from stored recap HTML / plain text."""
    from bs4 import BeautifulSoup

    title = (subject or '').strip() or 'Game Recap'
    summary = ''
    stats_rows = []
    games_rows = []
    date_label = ''

    soup = BeautifulSoup(html_body or '', 'html.parser')
    h1 = soup.find('h1')
    if h1:
        title = h1.get_text(' ', strip=True) or title
        # "Volleyball Recap - 07/16/2026" → date bit
        if ' - ' in title:
            date_label = title.rsplit(' - ', 1)[-1].strip()

    summary_el = soup.select_one('.summary-text')
    if summary_el:
        summary = _ig_summary_text_from_html(summary_el)
    elif plain_text_body:
        # Fall back to plain text SUMMARY section.
        plain = plain_text_body.replace('\r\n', '\n')
        if '\nSUMMARY\n' in plain:
            chunk = plain.split('\nSUMMARY\n', 1)[1]
            for stop in ('\nPLAYER STATS\n', '\nGAMES'):
                if stop in chunk:
                    chunk = chunk.split(stop, 1)[0]
            summary = chunk.strip()
    summary = _ig_normalize_summary_paragraphs(summary)

    stats_table = soup.select_one('table.stats-table')
    if stats_table:
        for tr in stats_table.select('tbody tr'):
            cells = [td.get_text(' ', strip=True) for td in tr.find_all(['td', 'th'])]
            if len(cells) >= 5:
                stats_rows.append({
                    'rank': cells[0],
                    'player': cells[1],
                    'w': cells[2],
                    'l': cells[3],
                    'win_pct': cells[4],
                    'diff': cells[5] if len(cells) > 5 else '',
                })

    def _team_cell_text(td):
        if td is None:
            return ''
        names = [
            a.get_text(' ', strip=True)
            for a in td.select('a.player-name, .player-name, a')
            if a.get_text(' ', strip=True)
        ]
        if names:
            return ' & '.join(names)
        # Fallback: block-level names become newlines in get_text.
        return ' & '.join(
            part.strip() for part in td.get_text('\n', strip=True).split('\n') if part.strip()
        )

    games_table = soup.select_one('table.games-table')
    if games_table:
        for tr in games_table.select('tbody tr'):
            cells = tr.find_all(['td', 'th'])
            if len(cells) < 4:
                continue
            time_cell = cells[0].get_text(' ', strip=True)
            if len(cells) >= 5:
                games_rows.append({
                    'time': time_cell,
                    'winners': _team_cell_text(cells[1]),
                    'w_score': cells[2].get_text(' ', strip=True),
                    'losers': _team_cell_text(cells[3]),
                    'l_score': cells[4].get_text(' ', strip=True),
                })
            else:
                games_rows.append({
                    'time': time_cell,
                    'winners': _team_cell_text(cells[1]),
                    'w_score': cells[2].get_text(' ', strip=True) if len(cells) > 2 else '',
                    'losers': _team_cell_text(cells[3]) if len(cells) > 3 else '',
                    'l_score': '',
                })

    hero = (hero_image_url or '').strip()
    if not hero:
        img = soup.select_one('.hero-image-card img')
        if img and img.get('src'):
            hero = img['src'].strip()

    section_title = title
    if 'Recap' in title:
        section_title = title.split('Recap')[0].strip() + ' Recap'
        if section_title == ' Recap':
            section_title = title

    return {
        'title': title,
        'section_title': section_title,
        'date_label': date_label,
        'summary': summary,
        'stats_rows': stats_rows,
        'games_rows': games_rows,
        'hero_image_url': hero,
    }


def _ig_new_canvas():
    from PIL import Image

    return Image.new('RGB', (IG_SLIDE_W, IG_SLIDE_H), IG_BG)


def _ig_render_photo_slide(data):
    import io
    from PIL import Image, ImageDraw, ImageOps

    canvas = _ig_new_canvas()
    draw = ImageDraw.Draw(canvas)
    hero_url = data.get('hero_image_url') or ''

    if hero_url:
        try:
            raw, _path = _load_hero_image_bytes(hero_url)
            img = Image.open(io.BytesIO(raw))
            img = ImageOps.exif_transpose(img)
            img = img.convert('RGB')
            resample = _pil_lanczos()
            # Fill the full Instagram 4:5 frame (no blur letterboxing).
            fitted = ImageOps.fit(img, (IG_SLIDE_W, IG_SLIDE_H), method=resample)
            canvas.paste(fitted, (0, 0))
            # Bottom gradient for title readability.
            overlay = Image.new('RGBA', (IG_SLIDE_W, IG_SLIDE_H), (0, 0, 0, 0))
            odraw = ImageDraw.Draw(overlay)
            grad_h = 360
            for i in range(grad_h):
                alpha = int(220 * (i / (grad_h - 1)))
                y = IG_SLIDE_H - grad_h + i
                odraw.line([(0, y), (IG_SLIDE_W, y)], fill=(11, 15, 20, alpha))
            canvas = Image.alpha_composite(canvas.convert('RGBA'), overlay).convert('RGB')
            draw = ImageDraw.Draw(canvas)
        except Exception:
            # Fall through to title card if hero can't load.
            hero_url = ''

    if not hero_url:
        # Branded placeholder when there's no illustration.
        pad = 80
        draw.rounded_rectangle(
            [pad, pad, IG_SLIDE_W - pad, IG_SLIDE_H - pad],
            radius=36,
            fill=IG_PANEL,
            outline=IG_ACCENT,
            width=3,
        )
        eyebrow_font = _ig_load_font(28, bold=True)
        title_font = _ig_load_font(52, bold=True)
        sub_font = _ig_load_font(30)
        note_font = _ig_load_font(34)
        cy = IG_SLIDE_H // 2 - 80
        eyebrow = 'GAME RECAP'
        ew = _ig_text_width(draw, eyebrow, eyebrow_font)
        draw.text(((IG_SLIDE_W - ew) / 2, cy), eyebrow, font=eyebrow_font, fill=IG_ACCENT)
        cy += 44
        bar_w = 72
        draw.rectangle(
            [(IG_SLIDE_W - bar_w) // 2, cy, (IG_SLIDE_W + bar_w) // 2, cy + 4],
            fill=IG_ACCENT,
        )
        cy += 28
        title = data.get('section_title') or 'Game Recap'
        for line in _ig_wrap_text(draw, title, title_font, IG_SLIDE_W - pad * 2 - 40)[:3]:
            tw = _ig_text_width(draw, line, title_font)
            draw.text(((IG_SLIDE_W - tw) / 2, cy), line, font=title_font, fill=IG_TEXT)
            cy += 60
        if data.get('date_label'):
            sw = _ig_text_width(draw, data['date_label'], sub_font)
            draw.text(((IG_SLIDE_W - sw) / 2, cy), data['date_label'], font=sub_font, fill=IG_MUTED)
        return canvas

    # Title over photo
    title = data.get('title') or 'Game Recap'
    title_font = _ig_load_font(44, bold=True)
    lines = _ig_wrap_text(draw, title, title_font, IG_SLIDE_W - 96)
    y = IG_SLIDE_H - 72 - int(len(lines[:3]) * 52)
    for line in lines[:3]:
        tw = _ig_text_width(draw, line, title_font)
        draw.text(((IG_SLIDE_W - tw) / 2, y), line, font=title_font, fill=IG_TEXT)
        y += 52
    return canvas


def _ig_render_summary_slide(data):
    from PIL import ImageDraw

    canvas = _ig_new_canvas()
    draw = ImageDraw.Draw(canvas)
    y = _ig_draw_header(draw, 'AI Summary', data.get('date_label') or '')
    pad = 72
    panel = [pad - 16, y, IG_SLIDE_W - pad + 16, IG_SLIDE_H - pad]
    draw.rounded_rectangle(panel, radius=28, fill=IG_PANEL)
    inner_pad = 40
    text = (data.get('summary') or '').strip() or 'No summary available.'
    max_w = IG_SLIDE_W - pad * 2 - inner_pad * 2
    max_h = panel[3] - panel[1] - inner_pad * 2
    lines, font, line_h = _ig_fit_wrapped_lines(
        draw, text, max_w, max_h, size_start=40, size_min=24, bold=False, line_gap=1.35,
    )
    ty = panel[1] + inner_pad
    line_gap = int(line_h * 1.35)
    para_gap = int(line_h * 0.75)
    for line in lines:
        if not line:
            ty += para_gap
            continue
        draw.text((pad + inner_pad, ty), line, font=font, fill=IG_TEXT)
        ty += line_gap
    return canvas


def _ig_render_stats_slide(data):
    from PIL import ImageDraw

    canvas = _ig_new_canvas()
    draw = ImageDraw.Draw(canvas)
    y = _ig_draw_header(draw, 'Player Stats', data.get('date_label') or '')
    rows = data.get('stats_rows') or []
    pad = 56
    if not rows:
        empty = _ig_load_font(34)
        msg = 'No stats available.'
        mw = _ig_text_width(draw, msg, empty)
        draw.text(((IG_SLIDE_W - mw) / 2, y + 40), msg, font=empty, fill=IG_MUTED)
        return canvas

    # Column layout
    cols = [
        ('#', 70, 'center'),
        ('Player', 340, 'left'),
        ('W', 90, 'center'),
        ('L', 90, 'center'),
        ('Win %', 140, 'center'),
        ('+/-', 120, 'center'),
    ]
    table_w = sum(c[1] for c in cols)
    x0 = (IG_SLIDE_W - table_w) // 2
    available = IG_SLIDE_H - y - pad - 40
    row_h = min(72, max(44, available // (len(rows) + 1)))
    header_font = _ig_load_font(max(22, min(28, row_h - 18)), bold=True)
    cell_font = _ig_load_font(max(24, min(34, row_h - 14)))
    name_font = _ig_load_font(max(24, min(34, row_h - 14)), bold=True)

    # Header row
    hx = x0
    for label, width, align in cols:
        tw = _ig_text_width(draw, label, header_font)
        if align == 'center':
            tx = hx + (width - tw) / 2
        else:
            tx = hx + 8
        draw.text((tx, y + (row_h - 28) / 2), label, font=header_font, fill=IG_MUTED)
        hx += width
    y += row_h
    draw.line([(x0, y), (x0 + table_w, y)], fill=(255, 255, 255, 40), width=2)
    y += 8

    for i, row in enumerate(rows):
        if y + row_h > IG_SLIDE_H - pad:
            # Overflow indicator
            more = f'+{len(rows) - i} more'
            mf = _ig_load_font(26)
            mw = _ig_text_width(draw, more, mf)
            draw.text(((IG_SLIDE_W - mw) / 2, y + 8), more, font=mf, fill=IG_MUTED)
            break
        if i % 2 == 0:
            draw.rounded_rectangle(
                [x0 - 8, y, x0 + table_w + 8, y + row_h - 4],
                radius=10,
                fill=(24, 32, 44),
            )
        values = [
            (row.get('rank') or '', cols[0][1], 'center', IG_ACCENT, header_font),
            (row.get('player') or '', cols[1][1], 'left', IG_TEXT, name_font),
            (row.get('w') or '', cols[2][1], 'center', IG_TEXT, cell_font),
            (row.get('l') or '', cols[3][1], 'center', IG_TEXT, cell_font),
            (row.get('win_pct') or '', cols[4][1], 'center', IG_TEXT, cell_font),
            (row.get('diff') or '', cols[5][1], 'center', IG_TEXT, cell_font),
        ]
        diff = (row.get('diff') or '').strip()
        if diff.startswith('+') and diff not in ('+', '+0', '0'):
            values[5] = (diff, cols[5][1], 'center', IG_WIN, name_font)
        elif diff.startswith('-'):
            values[5] = (diff, cols[5][1], 'center', IG_LOSS, name_font)

        hx = x0
        for text, width, align, color, font in values:
            # Truncate long player names
            display = text
            while display and _ig_text_width(draw, display, font) > width - 12:
                display = display[:-2] + '…' if len(display) > 2 else display[:-1]
            tw = _ig_text_width(draw, display, font)
            if align == 'center':
                tx = hx + (width - tw) / 2
            else:
                tx = hx + 8
            th = _ig_text_height(draw, display or 'Ag', font)
            draw.text((tx, y + (row_h - 4 - th) / 2), display, font=font, fill=color)
            hx += width
        y += row_h
    return canvas


def _ig_render_games_slide(data):
    from PIL import ImageDraw

    canvas = _ig_new_canvas()
    draw = ImageDraw.Draw(canvas)
    games = data.get('games_rows') or []
    subtitle = f'{len(games)} game{"s" if len(games) != 1 else ""}'
    if data.get('date_label'):
        subtitle = f'{data["date_label"]} · {subtitle}'
    y = _ig_draw_header(draw, 'Games', subtitle)
    pad = 48
    if not games:
        empty = _ig_load_font(34)
        msg = 'No games available.'
        mw = _ig_text_width(draw, msg, empty)
        draw.text(((IG_SLIDE_W - mw) / 2, y + 40), msg, font=empty, fill=IG_MUTED)
        return canvas

    left = pad
    right = IG_SLIDE_W - pad
    inner = 22
    name_max_w = right - left - inner * 2
    available = IG_SLIDE_H - y - pad

    # Stacked card layout so full doubles names fit (no side-by-side squeeze):
    # time + score on top row, winners, then losers — each name can wrap full width.
    def _prepare(name_size):
        time_font = _ig_load_font(max(18, min(24, name_size - 6)))
        name_font = _ig_load_font(name_size, bold=True)
        score_font = _ig_load_font(max(24, min(36, name_size + 4)), bold=True)
        line_h = max(_ig_text_height(draw, 'Ag', name_font), name_size)
        gap = 1.22
        cards = []
        total_h = 0
        needs_smaller = False
        for game in games:
            winners = (game.get('winners') or '').replace('\n', ' & ').strip()
            losers = (game.get('losers') or '').replace('\n', ' & ').strip()
            w_all = _ig_wrap_text(draw, winners, name_font, name_max_w) or ['']
            l_all = _ig_wrap_text(draw, losers, name_font, name_max_w) or ['']
            if len(w_all) > 2 or len(l_all) > 2:
                needs_smaller = True
            w_lines = w_all[:2]
            l_lines = l_all[:2]
            w_score = (game.get('w_score') or '').strip()
            l_score = (game.get('l_score') or '').strip()
            if w_score and l_score:
                score_text = f'{w_score}  –  {l_score}'
            elif w_score or l_score:
                score_text = f'{w_score or "–"}  –  {l_score or "–"}'
            else:
                score_text = '–'
            names_h = int((len(w_lines) + len(l_lines)) * line_h * gap) + 6
            card_h = 14 + 30 + names_h + 14
            cards.append({
                'time': (game.get('time') or '').strip(),
                'w_lines': w_lines,
                'l_lines': l_lines,
                'score': score_text,
                'h': card_h,
            })
            total_h += card_h + 10
        return time_font, name_font, score_font, line_h, gap, cards, total_h, needs_smaller

    start_size = 30 if len(games) <= 6 else 26 if len(games) <= 8 else 22
    prepared = None
    for size in range(start_size, 17, -2):
        result = _prepare(size)
        time_font, name_font, score_font, line_h, gap, cards, total_h, needs_smaller = result
        prepared = result
        if total_h <= available and not needs_smaller:
            break

    time_font, name_font, score_font, line_h, gap, cards, total_h, _ = prepared
    if total_h < available:
        y += (available - total_h) // 2

    for i, card in enumerate(cards):
        if y + card['h'] > IG_SLIDE_H - pad + 8:
            more = f'+{len(cards) - i} more'
            mf = _ig_load_font(26)
            mw = _ig_text_width(draw, more, mf)
            draw.text(((IG_SLIDE_W - mw) / 2, y), more, font=mf, fill=IG_MUTED)
            break
        draw.rounded_rectangle(
            [left, y, right, y + card['h']],
            radius=16,
            fill=IG_PANEL,
        )
        cy = y + 12
        # Time left, score right on the same row.
        if card['time']:
            draw.text((left + inner, cy), card['time'], font=time_font, fill=IG_MUTED)
        sw = _ig_text_width(draw, card['score'], score_font)
        draw.text((right - inner - sw, cy - 2), card['score'], font=score_font, fill=IG_TEXT)
        cy += 32
        for line in card['w_lines']:
            draw.text((left + inner, cy), line, font=name_font, fill=IG_WIN)
            cy += int(line_h * gap)
        cy += 4
        for line in card['l_lines']:
            draw.text((left + inner, cy), line, font=name_font, fill=IG_LOSS)
            cy += int(line_h * gap)
        y += card['h'] + 10
    return canvas


def _ig_save_jpeg(img, path, quality=88):
    if img.mode != 'RGB':
        img = img.convert('RGB')
    tmp = f'{path}.tmp'
    img.save(tmp, format='JPEG', quality=quality, optimize=True)
    os.replace(tmp, path)
    return path


def build_instagram_slides(share_id, html_body, plain_text_body='', subject='',
                           hero_image_url=''):
    """Render and save 4 Instagram-ready square JPEGs for a recap.

    Returns list of absolute file paths in carousel order.
    """
    data = parse_recap_for_instagram(
        html_body,
        plain_text_body=plain_text_body,
        subject=subject,
        hero_image_url=hero_image_url,
    )
    out_dir = instagram_slides_dir(share_id)
    renderers = {
        'photo': _ig_render_photo_slide,
        'summary': _ig_render_summary_slide,
        'stats': _ig_render_stats_slide,
        'games': _ig_render_games_slide,
    }
    paths = []
    for filename, kind in IG_SLIDE_FILES:
        img = renderers[kind](data)
        path = os.path.join(out_dir, filename)
        _ig_save_jpeg(img, path)
        paths.append(path)
    version_path = os.path.join(out_dir, 'version.txt')
    tmp_version = f'{version_path}.tmp'
    with open(tmp_version, 'w', encoding='utf-8') as handle:
        handle.write(str(IG_SLIDE_VERSION))
    os.replace(tmp_version, version_path)
    return paths


def ensure_instagram_slides(share_id, html_body, plain_text_body='', subject='',
                            hero_image_url='', force=False):
    """Build slides if missing (or force=True). Returns list of paths."""
    if not force:
        existing = list_instagram_slide_paths(share_id)
        if existing:
            return existing
    try:
        return build_instagram_slides(
            share_id,
            html_body,
            plain_text_body=plain_text_body,
            subject=subject,
            hero_image_url=hero_image_url,
        )
    except Exception as exc:
        try:
            current_app.logger.exception(
                'Failed to build Instagram slides for %s: %s', share_id, exc,
            )
        except Exception:
            pass
        return []


def build_instagram_slides_zip_bytes(share_id):
    """Return zip bytes of the 4 Instagram slides, or None if missing."""
    import io
    import zipfile

    paths = list_instagram_slide_paths(share_id)
    if not paths:
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            zf.write(path, arcname=os.path.basename(path))
    return buf.getvalue()


_UPLOAD_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
_MAX_UPLOAD_IMAGE_BYTES = 8 * 1024 * 1024


def save_uploaded_email_image(file_storage, prefix=''):
    """Validate and save a user-uploaded illustration. Returns (url, abs_path)."""
    if not file_storage or not getattr(file_storage, 'filename', None):
        raise ValueError('Choose an image file to upload.')
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in _UPLOAD_IMAGE_EXTENSIONS:
        raise ValueError('Image must be JPG, PNG, WebP, or GIF.')
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size <= 0:
        raise ValueError('That image file is empty.')
    if size > _MAX_UPLOAD_IMAGE_BYTES:
        raise ValueError('Image must be 8 MB or smaller.')
    raw = file_storage.read()
    if not raw:
        raise ValueError('Could not read that image file.')
    # Normalize extension for storage (jpeg → jpg).
    store_ext = 'jpg' if ext in ('.jpg', '.jpeg') else ext.lstrip('.')
    return _save_email_image(raw, store_ext, prefix=prefix)


def email_images_dir():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'email_images')
    os.makedirs(path, exist_ok=True)
    return path


def delete_solo_image_files(solo_images):
    """Delete files listed in a solo_images [{url, path, name}, ...] list."""
    deleted = 0
    for item in solo_images or []:
        path = (item or {}).get('path')
        if not path:
            url = (item or {}).get('url') or ''
            marker = '/static/email_images/'
            if marker in url:
                filename = url.split(marker, 1)[1].split('?', 1)[0]
                path = os.path.join(email_images_dir(), os.path.basename(filename))
        if not path or not os.path.isfile(path):
            continue
        # Only remove temporary solo caricatures, never the group hero.
        if not os.path.basename(path).startswith(SOLO_IMAGE_PREFIX):
            continue
        try:
            os.remove(path)
            deleted += 1
        except OSError:
            pass
    return deleted


def cleanup_expired_solo_images(max_age_hours=None):
    """Remove temporary solo caricature files older than max_age_hours."""
    import time

    hours = SOLO_IMAGE_MAX_AGE_HOURS if max_age_hours is None else max_age_hours
    cutoff = time.time() - (float(hours) * 3600)
    directory = email_images_dir()
    deleted = 0
    for name in os.listdir(directory):
        if not name.startswith(SOLO_IMAGE_PREFIX):
            continue
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            if os.path.getmtime(path) >= cutoff:
                continue
            os.remove(path)
            deleted += 1
        except OSError:
            continue
    return deleted


def filter_existing_solo_images(solo_images):
    """Keep only solo entries whose files still exist on disk."""
    kept = []
    for item in solo_images or []:
        if not item:
            continue
        path = _solo_image_path(item)
        if path and os.path.isfile(path):
            kept.append({**item, 'path': path})
    return kept


def _solo_image_path(item):
    """Resolve a solo image dict to an absolute file path if possible."""
    if not item:
        return None
    path = item.get('path')
    if path and os.path.isfile(path):
        return path
    url = item.get('url') or ''
    marker = '/static/email_images/'
    if marker not in url:
        return None
    filename = url.split(marker, 1)[1].split('?', 1)[0]
    path = os.path.join(email_images_dir(), os.path.basename(filename))
    return path if os.path.isfile(path) else None


def _ext_to_mime(path_or_ext):
    ext = os.path.splitext(path_or_ext)[1].lower().lstrip('.')
    if ext in ('jpg', 'jpeg'):
        return 'image/jpeg'
    if ext == 'gif':
        return 'image/gif'
    if ext == 'webp':
        return 'image/webp'
    return 'image/png'


def _load_caricatures_from_solo_images(players, solo_images):
    """Load on-disk solo files into {name: (raw_bytes, mime)} for players that have them."""
    by_name = {}
    for item in solo_images or []:
        name = (item or {}).get('name')
        if not name:
            continue
        by_name[name.strip().lower()] = item

    caricatures = {}
    loaded_solos = []
    for name in players:
        item = by_name.get((name or '').strip().lower())
        if not item:
            continue
        path = _solo_image_path(item)
        if not path:
            continue
        try:
            with open(path, 'rb') as handle:
                raw = handle.read()
        except OSError:
            continue
        if not raw:
            continue
        caricatures[name] = (raw, _ext_to_mime(path))
        loaded_solos.append({
            'name': name,
            'url': item.get('url') or '',
            'path': path,
        })
    return caricatures, loaded_solos


def build_solo_caricature_prompt(player_name, game_type='doubles', game_name=None):
    """Build the default solo caricature prompt (for preview/edit in the UI)."""
    from player_functions import (
        collect_player_ai_image_traits,
        collect_solo_reference_images,
    )

    name = (player_name or '').strip()
    trait_entries = collect_player_ai_image_traits([name]) if name else []
    trait_phrases = trait_entries[0].get('phrases', []) if trait_entries else []
    entry = collect_solo_reference_images(name) if name else None
    reference_parts = _solo_reference_parts_for_player(name, entry)
    has_reference_photos = any(part.get('inline_data') for part in reference_parts)
    return _build_solo_player_prompt(name, trait_phrases, has_reference_photos)


def generate_solo_caricature(
    api_key, player_name, game_type='doubles', game_name=None, custom_prompt=None,
):
    """Generate one temporary solo caricature for a player.

    Returns {name, url, path, prompt}. When custom_prompt is set, that text is
    used as the main illustration prompt (reference photos still attached).
    Requires a face photo and/or signature looks.
    """
    from player_functions import (
        collect_player_ai_image_traits,
        collect_solo_reference_images,
    )

    name = (player_name or '').strip()
    if not name:
        raise ValueError('Player name is required.')

    entry = collect_solo_reference_images(name)
    reference_parts = _solo_reference_parts_for_player(name, entry)
    has_reference_photos = any(part.get('inline_data') for part in reference_parts)
    trait_entries = collect_player_ai_image_traits([name])
    trait_phrases = trait_entries[0].get('phrases', []) if trait_entries else []
    if not _player_can_illustrate(has_reference_photos, trait_phrases):
        raise ValueError(
            f'{name} has no face photo or signature looks — cannot create an image.'
        )
    solo_prompt = (custom_prompt or '').strip()
    if not solo_prompt:
        solo_prompt = build_solo_caricature_prompt(
            name, game_type=game_type, game_name=game_name,
        )
    try:
        raw, mime = _generate_image_bytes(solo_prompt, api_key, reference_parts=reference_parts)
    except Exception as e:
        raise ImageGenerationError(
            _friendly_image_error(e, api_calls=1),
            image_prompt=_image_prompt_bundle(reference_parts, solo_prompt),
            solo_images=[],
        ) from e

    solo_url, solo_path = _save_email_image(
        raw, _mime_to_ext(mime), prefix=SOLO_IMAGE_PREFIX,
    )
    return {'name': name, 'url': solo_url, 'path': solo_path, 'prompt': solo_prompt}


def _image_prompt_bundle(reference_parts, prompt, image_label='[Reference image attached]'):
    """Serialize the full text sent to the image model (reference labels + prompt)."""
    lines = []
    for part in reference_parts or []:
        text = part.get('text')
        if text:
            lines.append(text)
        elif part.get('inline_data'):
            lines.append(image_label)
    lines.append('')
    lines.append('--- Main illustration prompt ---')
    lines.append(prompt)
    return '\n\n'.join(lines)


def _mime_to_ext(mime):
    if 'gif' in mime:
        return 'gif'
    if 'jpeg' in mime or 'jpg' in mime:
        return 'jpg'
    return 'png'


def _image_prompt_bundle_multipass(solo_passes, scene_reference_parts, scene_prompt):
    sections = ['=== Pass 1: Solo caricatures ===']
    for index, (_name, ref_parts, prompt) in enumerate(solo_passes, start=1):
        sections.append(f'--- Person {index} ---')
        sections.append(_image_prompt_bundle(ref_parts, prompt))
    sections.append('')
    sections.append('=== Pass 2: Group scene ===')
    sections.append(_image_prompt_bundle(
        scene_reference_parts, scene_prompt, image_label='[Generated caricature attached]',
    ))
    return '\n\n'.join(sections)


def _illustration_meta(player_names, game_type, games, selected_players=None):
    all_players = _ordered_email_image_players(player_names)
    api_calls = (len(all_players) + 1) if all_players else 0
    return {
        'strategy': 'two_pass',
        'illustrated_players': all_players,
        'solo_players': all_players,
        'total_players': len(all_players),
        'api_calls': api_calls,
        'note': _illustration_status_note(all_players),
    }


def _illustration_status_note(all_players):
    if not all_players:
        return ''
    return (
        f'Illustration uses one caricature per player, then a group scene '
        f'({len(all_players)} players).'
    )


def _generate_email_hero_image_two_pass(
    api_key, game_type, players, game_name=None, image_details='',
    existing_solo_images=None, reuse_existing_solos=False,
    custom_scene_prompt=None, scene_players=None, solo_prompt_builder=None,
    scene_prompt_builder=None,
):
    """Solo caricature per illustratable player, then one group scene.

    Only players with a face photo and/or signature looks get a solo
    caricature. Those solos are saved temporarily (creator preview only;
    auto-expire), then attached as references for the group scene. Only the
    group illustration is kept permanently.

    When reuse_existing_solos is True, any matching on-disk solos in
    existing_solo_images are kept and only missing players are regenerated.

    When custom_scene_prompt is set, that text is used as the group scene
    prompt (caricature references still attached).

    solo_prompt_builder(name, trait_phrases, has_refs) overrides the default
    solo prompt. scene_prompt_builder(players, ...) overrides the default scene
    prompt when custom_scene_prompt is empty.
    """
    from player_functions import (
        collect_player_ai_image_traits,
        collect_solo_reference_images,
    )

    players = _dedupe_players_preserve_order(players)
    if not players:
        raise ValueError('No players in roster for illustration')

    # Group scene includes only players who got (or reused) a solo caricature.
    scene_roster = list(players)
    build_solo = solo_prompt_builder or _build_solo_player_prompt

    caricatures = {}
    solo_images = []
    if reuse_existing_solos and existing_solo_images:
        caricatures, solo_images = _load_caricatures_from_solo_images(
            players, existing_solo_images,
        )

    trait_entries = collect_player_ai_image_traits(players)
    traits_by_name = {entry['name']: entry for entry in trait_entries}

    solo_passes = []
    for name in players:
        if name in caricatures:
            solo_passes.append((name, [], f'[Reused existing solo caricature for {name}]'))
            continue

        entry = collect_solo_reference_images(name)
        reference_parts = _solo_reference_parts_for_player(name, entry)
        trait_entry = traits_by_name.get(name)
        trait_phrases = trait_entry.get('phrases', []) if trait_entry else []
        has_reference_photos = any(part.get('inline_data') for part in reference_parts)
        if not _player_can_illustrate(has_reference_photos, trait_phrases):
            # No face photo and no signature looks — skip this player entirely.
            continue
        solo_prompt = build_solo(name, trait_phrases, has_reference_photos)
        solo_passes.append((name, reference_parts, solo_prompt))
        try:
            raw, mime = _generate_image_bytes(solo_prompt, api_key, reference_parts=reference_parts)
        except Exception as e:
            partial_prompt = _image_prompt_bundle_multipass(
                solo_passes, [], 'Group scene not reached — solo caricature failed.',
            )
            raise ImageGenerationError(
                _friendly_image_error(e, api_calls=len(solo_passes)),
                image_prompt=partial_prompt,
                solo_images=solo_images,
            ) from e
        caricatures[name] = (raw, mime)
        solo_url, solo_path = _save_email_image(
            raw, _mime_to_ext(mime), prefix=SOLO_IMAGE_PREFIX,
        )
        solo_images.append({
            'name': name,
            'url': solo_url,
            'path': solo_path,
            'prompt': solo_prompt,
        })

    # Keep solo_images in roster order for stable UI.
    by_name = {(item.get('name') or '').strip().lower(): item for item in solo_images}
    solo_images = [by_name[n.strip().lower()] for n in players if n.strip().lower() in by_name]

    scene_for_refs = [name for name in scene_roster if name in caricatures]
    if not scene_for_refs:
        raise ValueError(
            'No players have a face photo or signature looks to illustrate.'
        )
    scene_refs = _reference_parts_from_caricatures(scene_for_refs, caricatures)
    if (custom_scene_prompt or '').strip():
        scene_prompt = custom_scene_prompt.strip()
    elif scene_prompt_builder:
        scene_prompt = scene_prompt_builder(scene_for_refs)
    else:
        scene_prompt = _build_scene_image_prompt(
            game_type, scene_for_refs, game_name=game_name, image_details=image_details,
        )
    image_prompt = _image_prompt_bundle_multipass(solo_passes, scene_refs, scene_prompt)
    try:
        raw, mime = _generate_image_bytes(
            scene_prompt, api_key, reference_parts=scene_refs, aspect_ratio='4:5',
        )
    except Exception as e:
        raise ImageGenerationError(
            _friendly_image_error(e, api_calls=len(players) + 1),
            image_prompt=image_prompt,
            solo_images=solo_images,
        ) from e
    # Guarantee Instagram 4:5 even if the model returns a near-miss ratio.
    raw, mime = _normalize_image_bytes_to_aspect(raw, ratio_w=4, ratio_h=5)
    url, path = _save_email_image(raw, _mime_to_ext(mime))
    return url, path, image_prompt, solo_images, scene_prompt


def generate_flyer_image(
    api_key, players, game_type, event_date='', event_time='', location='',
    game_name=None, image_details='', existing_solo_images=None,
    reuse_existing_solos=False, custom_scene_prompt=None,
    custom_solo_prompts=None,
):
    """Generate flyer: exaggerated solo caricatures, then Instagram 4:5 group flyer.

    custom_solo_prompts may be {player_name: prompt} to override specific solos.
    Returns (url, path, image_prompt, solo_images, scene_prompt).
    """
    players = _dedupe_players_preserve_order(players)
    if not players:
        raise ValueError('Select at least one player for the flyer')

    overrides = {}
    for key, value in (custom_solo_prompts or {}).items():
        clean_key = (key or '').strip().lower()
        clean_val = (value or '').strip()
        if clean_key and clean_val:
            overrides[clean_key] = clean_val

    def solo_builder(name, trait_phrases, has_refs):
        override = overrides.get((name or '').strip().lower())
        if override:
            return override
        return _build_solo_player_prompt(name, trait_phrases, has_refs)

    def scene_builder(scene_players):
        return build_flyer_scene_prompt(
            scene_players,
            game_type,
            event_date=event_date,
            event_time=event_time,
            location=location,
            game_name=game_name,
            image_details=image_details,
        )

    return _generate_email_hero_image_two_pass(
        api_key,
        game_type,
        players,
        game_name=game_name,
        image_details=image_details,
        existing_solo_images=existing_solo_images,
        reuse_existing_solos=reuse_existing_solos,
        custom_scene_prompt=custom_scene_prompt,
        scene_players=players,
        solo_prompt_builder=solo_builder,
        scene_prompt_builder=scene_builder,
    )


def generate_flyer_solo_caricature(api_key, player_name, custom_prompt=None):
    """Generate one flyer-style solo caricature (high exaggeration).

    Requires a face photo and/or signature looks.
    """
    from player_functions import (
        collect_player_ai_image_traits,
        collect_solo_reference_images,
    )

    name = (player_name or '').strip()
    if not name:
        raise ValueError('Player name is required.')

    entry = collect_solo_reference_images(name)
    reference_parts = _solo_reference_parts_for_player(name, entry)
    has_reference_photos = any(part.get('inline_data') for part in reference_parts)
    trait_entries = collect_player_ai_image_traits([name])
    trait_phrases = trait_entries[0].get('phrases', []) if trait_entries else []
    if not _player_can_illustrate(has_reference_photos, trait_phrases):
        raise ValueError(
            f'{name} has no face photo or signature looks — cannot create an image.'
        )
    solo_prompt = (custom_prompt or '').strip() or build_flyer_solo_prompt(name)
    try:
        raw, mime = _generate_image_bytes(solo_prompt, api_key, reference_parts=reference_parts)
    except Exception as e:
        raise ImageGenerationError(
            _friendly_image_error(e, api_calls=1),
            image_prompt=_image_prompt_bundle(reference_parts, solo_prompt),
            solo_images=[],
        ) from e

    solo_url, solo_path = _save_email_image(
        raw, _mime_to_ext(mime), prefix=SOLO_IMAGE_PREFIX,
    )
    return {'name': name, 'url': solo_url, 'path': solo_path, 'prompt': solo_prompt}


def generate_email_hero_image(
    api_key, game_type, games, player_names, game_name=None, image_details='',
    existing_solo_images=None, reuse_existing_solos=False, custom_scene_prompt=None,
    selected_players=None,
):
    """Generate hero image: solo caricature for every roster player, then group scene."""
    all_players = _ordered_email_image_players(player_names)
    if not all_players:
        raise ValueError('No players in roster for illustration')
    return _generate_email_hero_image_two_pass(
        api_key, game_type, all_players, game_name=game_name,
        image_details=image_details,
        existing_solo_images=existing_solo_images,
        reuse_existing_solos=reuse_existing_solos,
        custom_scene_prompt=custom_scene_prompt,
        scene_players=all_players,
    )


def _try_generate_email_hero_image(
    api_key, game_type, games, player_names, game_name=None, image_mode='none',
    image_details='', existing_solo_images=None, reuse_existing_solos=False,
    custom_scene_prompt=None, selected_players=None,
):
    mode = _normalize_image_mode(image_mode)
    if mode == 'none':
        return None, None, None, '', None
    meta = _illustration_meta(
        player_names, game_type, games, selected_players=selected_players,
    )
    try:
        url, path, image_prompt, solo_images, scene_prompt = generate_email_hero_image(
            api_key, game_type, games, player_names,
            game_name=game_name,
            image_details=image_details,
            existing_solo_images=existing_solo_images,
            reuse_existing_solos=reuse_existing_solos,
            custom_scene_prompt=custom_scene_prompt,
            selected_players=selected_players,
        )
        meta = {**meta, 'scene_prompt': scene_prompt or ''}
        if solo_images:
            meta = {**meta, 'solo_images': solo_images}
        return url, path, None, image_prompt, meta
    except Exception as e:
        err = _friendly_image_error(e, api_calls=meta.get('api_calls', 1))
        image_prompt = getattr(e, 'image_prompt', None)
        solo_images = []
        if isinstance(e, ImageGenerationError):
            if e.image_prompt:
                image_prompt = e.image_prompt
            solo_images = e.solo_images or []
        if solo_images:
            meta = {**meta, 'solo_images': solo_images}
        try:
            current_app.logger.warning('AI email image generation failed: %s', err)
        except Exception:
            pass
        return None, None, err, image_prompt or '', meta


def email_html_for_inline_preview(html_body):
    """Extract email body with scoped styles for inline display on the preview page."""
    return _email_html_for_embedded_display(html_body, wrapper_class='sr-email-inline')


def recap_html_for_page(html_body):
    """Prepare stored email HTML for a public recap page."""
    from bs4 import BeautifulSoup

    if not html_body or not str(html_body).strip():
        return '<p>No recap content.</p>'

    soup = BeautifulSoup(html_body, 'html.parser')
    for el in soup.select('.opt-in-section'):
        el.decompose()
    cleaned = str(soup)
    return _email_html_for_embedded_display(cleaned, wrapper_class='recap-body')


def _email_html_for_embedded_display(html_body, wrapper_class='sr-email-inline'):
    """Extract email body with scoped styles for embedding in a host page."""
    import re
    from bs4 import BeautifulSoup

    if not html_body or not str(html_body).strip():
        return '<p>No email content.</p>'

    soup = BeautifulSoup(html_body, 'html.parser')
    styles = []
    for tag in soup.find_all('style'):
        css = tag.get_text() or ''
        css = re.sub(r'\bbody\b', f'.{wrapper_class}', css)
        css = re.sub(r'\bhtml\b', f'.{wrapper_class}', css)
        styles.append(css)
    body = soup.find('body')
    content = body.decode_contents() if body else html_body
    style_block = f'<style>{"".join(styles)}</style>' if styles else ''
    return f'{style_block}<div class="{wrapper_class}">{content}</div>'


def format_name_for_email(name):
    if not name:
        return ""
    return str(name).strip()


def _player_page_url(game_type, year, name):
    """Absolute URL to a player's stats page for the given game type."""
    clean = format_name_for_email(name)
    if not clean:
        return ''
    year_str = str(year or datetime.now().year)
    encoded = quote(clean, safe='')
    if game_type == 'vollis':
        return f'{SITE_BASE_URL}/vollis_player/{year_str}/{encoded}/'
    if game_type == 'other':
        return f'{SITE_BASE_URL}/other_player/{year_str}/{encoded}/'
    return f'{SITE_BASE_URL}/player/{year_str}/{encoded}/'


def player_name_link_html(game_type, year, name, css_class='player-name'):
    """Linked player name for email/recap HTML (escapes display text)."""
    clean = format_name_for_email(name)
    if not clean:
        return ''
    url = _player_page_url(game_type, year, clean)
    display = html.escape(clean)
    class_attr = f' class="{css_class}"' if css_class else ''
    return (
        f'<a{class_attr} href="{url}" '
        f'style="color:inherit;text-decoration:none;">'
        f'{display}</a>'
    )


def _plain_footer_lines(stats_link, date_obj):
    return [
        '',
        f'View {date_obj.year} stats: {stats_link}',
        f'Get all future summaries: {SITE_BASE_URL}/opt_in_ai_emails?email={EMAIL_PLACEHOLDER}',
        f'Unsubscribe: {SITE_BASE_URL}/opt_out_ai_emails?email={EMAIL_PLACEHOLDER}',
    ]


def _format_recap_date_long(date_obj):
    return date_obj.strftime('%B ') + str(date_obj.day) + f', {date_obj.year}'


def _plain_game_time(game):
    if len(game) > 1 and game[1]:
        date_time_str = str(game[1]).strip()
        parts = date_time_str.split()
        if len(parts) > 1:
            return ' '.join(parts[1:]).strip()
        if parts:
            return parts[0]
    return '-'


def _plain_game_time_dict(game):
    game_date = game.get('game_date', '')
    if game_date:
        parts = str(game_date).strip().split()
        if len(parts) > 1:
            return ' '.join(parts[1:]).strip()
        if parts:
            return parts[0]
    return '-'


def _email_game_time_cell(game, as_dict=False):
    """Compact time for email games tables (drop timezone parenthetical)."""
    raw = _plain_game_time_dict(game) if as_dict else _plain_game_time(game)
    if raw == '-':
        return raw
    paren = raw.find(' (')
    if paren > 0:
        return raw[:paren]
    return raw


def create_doubles_email_plain_text(summary, stats, games, date_obj):
    formatted_date = _format_recap_date_long(date_obj)
    lines = [f'Volleyball Recap — {formatted_date}', '']

    if summary:
        lines.append('SUMMARY')
        lines.append(summary.strip())
        lines.append('')

    lines.append('PLAYER STATS')
    for index, stat in enumerate(stats, start=1):
        player_name = stat[0]
        wins, losses = stat[1], stat[2]
        win_pct = stat[3] * 100
        differential = stat[4]
        diff_sign = '+' if differential >= 0 else ''
        lines.append(
            f'{index}. {player_name} — {wins}-{losses} ({win_pct:.0f}%), {diff_sign}{differential}'
        )
    lines.append('')

    lines.append(f'GAMES ({len(games)})')
    for game in games:
        time_display = _plain_game_time(game)
        w1, w2 = game[2] or '', game[3] or ''
        l1, l2 = game[5] or '', game[6] or ''
        w_score = game[4] if len(game) > 4 and game[4] is not None else ''
        l_score = game[7] if len(game) > 7 and game[7] is not None else ''
        lines.append(
            f'- {time_display}: {w1} & {w2} beat {l1} & {l2} ({w_score}-{l_score})'
        )

    lines.extend(_plain_footer_lines(f'{SITE_BASE_URL}/stats/{date_obj.year}/', date_obj))
    return '\n'.join(lines)


def create_vollis_email_plain_text(summary, stats, games, date_obj):
    formatted_date = _format_recap_date_long(date_obj)
    lines = [f'Vollis Recap — {formatted_date}', '']

    if summary:
        lines.append('SUMMARY')
        lines.append(summary.strip())
        lines.append('')

    lines.append('PLAYER STATS')
    for index, stat in enumerate(stats, start=1):
        player_name = stat[0]
        wins, losses = stat[1], stat[2]
        win_pct = stat[3] * 100
        lines.append(f'{index}. {player_name} — {wins}-{losses} ({win_pct:.0f}%)')
    lines.append('')

    lines.append(f'GAMES ({len(games)})')
    for game in games:
        time_display = _plain_game_time(game)
        winner = game[2] or ''
        loser = game[4] or ''
        w_score = game[3] if len(game) > 3 and game[3] is not None else ''
        l_score = game[5] if len(game) > 5 and game[5] is not None else ''
        lines.append(f'- {time_display}: {winner} beat {loser} ({w_score}-{l_score})')

    lines.extend(_plain_footer_lines(f'{SITE_BASE_URL}/vollis_stats/{date_obj.year}/', date_obj))
    return '\n'.join(lines)


def create_other_email_plain_text(summary, stats, games, date_obj, game_name_label=''):
    formatted_date = _format_recap_date_long(date_obj)
    title = game_name_label or 'Game'
    lines = [f'{title} Recap — {formatted_date}', '']

    if summary:
        lines.append('SUMMARY')
        lines.append(summary.strip())
        lines.append('')

    lines.append('PLAYER STATS')
    for index, stat in enumerate(stats, start=1):
        player_name = stat[0]
        wins, losses = stat[1], stat[2]
        win_pct = stat[3] * 100
        lines.append(f'{index}. {player_name} — {wins}-{losses} ({win_pct:.0f}%)')
    lines.append('')

    lines.append(f'GAMES ({len(games)})')
    for game in games:
        time_display = _plain_game_time_dict(game)
        winners = ', '.join(w['name'] for w in game.get('winners', []) if w.get('name'))
        losers = ', '.join(l['name'] for l in game.get('losers', []) if l.get('name'))
        w_score = game.get('winner_score') or ''
        l_score = game.get('loser_score') or ''
        lines.append(
            f'- {time_display}: {winners} beat {losers} ({w_score}-{l_score})'
        )

    lines.extend(_plain_footer_lines(f'{SITE_BASE_URL}/other_stats/{date_obj.year}/', date_obj))
    return '\n'.join(lines)


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
                    .stats-player a,
                    .stats-table a {{
                        color: inherit;
                        text-decoration: none;
                    }}
                    .diff-positive {{
                        color: #4ade80;
                        font-weight: 600;
                    }}
                    .diff-negative {{
                        color: #f87171;
                        font-weight: 600;
                    }}
                    {_email_games_table_styles()}
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

    stats_year = date_obj.year

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
                                    <td class="stats-player">{player_name_link_html('doubles', stats_year, player_name, css_class='')}</td>
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
                        <div class="games-table-wrap">
                        <table class="games-table">
                            <colgroup>
                                <col style="width:22%">
                                <col style="width:30%">
                                <col style="width:8%">
                                <col style="width:30%">
                                <col style="width:10%">
                            </colgroup>
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
        time_display = _email_game_time_cell(game)

        winner1 = player_name_link_html('doubles', stats_year, game[2]) if game[2] else ""
        winner2 = player_name_link_html('doubles', stats_year, game[3]) if game[3] else ""
        loser1 = player_name_link_html('doubles', stats_year, game[5]) if game[5] else ""
        loser2 = player_name_link_html('doubles', stats_year, game[6]) if game[6] else ""

        winner_score = game[4] if len(game) > 4 and game[4] is not None else ""
        loser_score = game[7] if len(game) > 7 and game[7] is not None else ""

        html_body += f"""
                                <tr>
                                    <td class="time-cell">{time_display}</td>
                                    <td class="team-cell winner-team">{winner1}{winner2}</td>
                                    <td class="score-winner">{winner_score}</td>
                                    <td class="team-cell loser-team">{loser1}{loser2}</td>
                                    <td class="score-loser">{loser_score}</td>
                                </tr>
                """

    html_body += """
                            </tbody>
                        </table>
                        </div>
                    </div>
            """

    html_body += f"""
                    <div class="footer">
                        <a href="{SITE_BASE_URL}/stats/{stats_year}/" class="link-button">View {stats_year} Stats</a>
                        <div class="opt-in-section">
                            <p class="opt-in-text">Want all future AI summaries?</p>
                            <a href="{SITE_BASE_URL}/opt_in_ai_emails?email={EMAIL_PLACEHOLDER}" class="opt-in-button">Yes, include me</a>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """

    return html_body


def build_doubles_email_payload(
    selected_game_ids, prompt_style='default', custom_prompt='', image_mode='none',
    image_details='', illustration_players=None,
):
    from stat_functions import calculate_stats_from_games, get_current_streaks_last_365_days, convert_ampm
    from player_functions import get_player_by_name

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError('Gemini API key not configured.')

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
    
    context = ''
    
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
            comment_str = f" - {game[9]}"
        context += f"- {winners} def. {losers} ({score}){comment_str}\n"

    style_instructions = _build_recap_style_instructions(prompt_style, context, custom_prompt)
    prompt = _build_recap_prompt(style_instructions, context)
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

    hero_image_url, hero_image_path, hero_image_error, image_prompt, illustration_meta = (
        _try_generate_email_hero_image(
            api_key, 'doubles', games, players_set, image_mode=image_mode,
            image_details=image_details,
            selected_players=illustration_players,
        )
    )
    html_body = create_doubles_email_html(
        summary, stats, games, date_obj, hero_image_url=hero_image_url,
    )
    plain_text_body = create_doubles_email_plain_text(summary, stats, games, date_obj)
    subject = generate_ai_email_subject(summary, 'doubles', date_obj)

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
        'plain_text_body': plain_text_body,
        'subject': subject,
        'game_type': 'doubles',
        'hero_image_url': hero_image_url,
        'hero_image_path': hero_image_path,
        'hero_image_error': hero_image_error,
        'date_obj': date_obj,
        'formatted_date': formatted_date,
        'ai_prompt': prompt,
        'style_instructions': _strip_recap_paragraph_limit(style_instructions),
        'image_prompt': image_prompt or '',
        'image_mode': _normalize_image_mode(image_mode),
        'image_details': (image_details or '').strip(),
        'illustration_note': (illustration_meta or {}).get('note', ''),
        'illustration_meta': illustration_meta or {},
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
                    .stats-player a, .stats-table a {{ color: inherit; text-decoration: none; }}
                    {_email_games_table_styles()}
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

    stats_year = date_obj.year

    for index, stat in enumerate(stats, start=1):
        player_name = stat[0]
        wins = stat[1]
        losses = stat[2]
        win_pct = stat[3] * 100

        html_body += f"""
                                <tr>
                                    <td class="stats-rank">{index}</td>
                                    <td class="stats-player">{player_name_link_html('vollis', stats_year, player_name, css_class='')}</td>
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
                        <div class="games-table-wrap">
                        <table class="games-table">
                            <colgroup>
                                <col style="width:22%">
                                <col style="width:30%">
                                <col style="width:8%">
                                <col style="width:30%">
                                <col style="width:10%">
                            </colgroup>
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
        time_display = _email_game_time_cell(game)

        winner = player_name_link_html('vollis', stats_year, game[2]) if game[2] else ""
        loser = player_name_link_html('vollis', stats_year, game[4]) if game[4] else ""
        winner_score = game[3] if len(game) > 3 and game[3] is not None else ""
        loser_score = game[5] if len(game) > 5 and game[5] is not None else ""

        html_body += f"""
                                <tr>
                                    <td class="time-cell">{time_display}</td>
                                    <td class="team-cell winner-team">{winner}</td>
                                    <td class="score-winner">{winner_score}</td>
                                    <td class="team-cell loser-team">{loser}</td>
                                    <td class="score-loser">{loser_score}</td>
                                </tr>
                """

    html_body += f"""
                            </tbody>
                        </table>
                        </div>
                    </div>
                    <div class="footer">
                        <a href="{SITE_BASE_URL}/vollis_stats/{stats_year}/" class="link-button">View {stats_year} Vollis Stats</a>
                        <div class="opt-in-section">
                            <p class="opt-in-text">Want all future AI summaries?</p>
                            <a href="{SITE_BASE_URL}/opt_in_ai_emails?email={EMAIL_PLACEHOLDER}" class="opt-in-button">Yes, include me</a>
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
                    .stats-player a, .stats-table a {{ color: inherit; text-decoration: none; }}
                    {_email_games_table_styles()}
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

    stats_year = date_obj.year

    for index, stat in enumerate(stats, start=1):
        player_name = stat[0]
        wins = stat[1]
        losses = stat[2]
        win_pct = stat[3] * 100

        html_body += f"""
                                <tr>
                                    <td class="stats-rank">{index}</td>
                                    <td class="stats-player">{player_name_link_html('other', stats_year, player_name, css_class='')}</td>
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
                        <div class="games-table-wrap">
                        <table class="games-table">
                            <colgroup>
                                <col style="width:22%">
                                <col style="width:30%">
                                <col style="width:8%">
                                <col style="width:30%">
                                <col style="width:10%">
                            </colgroup>
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
        time_display = _email_game_time_cell(game, as_dict=True)

        winners = game.get('winners', [])
        losers = game.get('losers', [])
        winner_names = "<br>".join(
            player_name_link_html('other', stats_year, w['name'], css_class='')
            for w in winners if w.get('name')
        )
        loser_names = "<br>".join(
            player_name_link_html('other', stats_year, l['name'], css_class='')
            for l in losers if l.get('name')
        )
        w_score = game.get('winner_score') or ''
        l_score = game.get('loser_score') or ''

        html_body += f"""
                                <tr>
                                    <td class="time-cell">{time_display}</td>
                                    <td class="team-cell winner-team">{winner_names}</td>
                                    <td class="score-winner">{w_score}</td>
                                    <td class="team-cell loser-team">{loser_names}</td>
                                    <td class="score-loser">{l_score}</td>
                                </tr>
                """

    html_body += f"""
                            </tbody>
                        </table>
                        </div>
                    </div>
                    <div class="footer">
                        <a href="{SITE_BASE_URL}/other_stats/{stats_year}/" class="link-button">View {stats_year} Other Stats</a>
                        <div class="opt-in-section">
                            <p class="opt-in-text">Want all future AI summaries?</p>
                            <a href="{SITE_BASE_URL}/opt_in_ai_emails?email={EMAIL_PLACEHOLDER}" class="opt-in-button">Yes, include me</a>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """

    return html_body


def build_vollis_email_payload(
    selected_game_ids, prompt_style='default', custom_prompt='', image_mode='none',
    image_details='', illustration_players=None,
):
    from vollis_functions import convert_vollis_ampm
    from player_functions import get_player_by_name

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError('Gemini API key not configured.')

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

    context = "Game Type: Vollis (1v1)\n\n"
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

    style_instructions = _build_recap_style_instructions(prompt_style, context, custom_prompt)
    prompt = _build_recap_prompt(style_instructions, context)
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

    hero_image_url, hero_image_path, hero_image_error, image_prompt, illustration_meta = (
        _try_generate_email_hero_image(
            api_key, 'vollis', games, players_set, image_mode=image_mode,
            image_details=image_details,
            selected_players=illustration_players,
        )
    )
    html_body = create_vollis_email_html(
        summary, stats, games, date_obj, hero_image_url=hero_image_url,
    )
    plain_text_body = create_vollis_email_plain_text(summary, stats, games, date_obj)
    subject = generate_ai_email_subject(summary, 'vollis', date_obj)

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
        'plain_text_body': plain_text_body,
        'subject': subject,
        'game_type': 'vollis',
        'hero_image_url': hero_image_url,
        'hero_image_path': hero_image_path,
        'hero_image_error': hero_image_error,
        'date_obj': date_obj,
        'formatted_date': formatted_date,
        'ai_prompt': prompt,
        'style_instructions': _strip_recap_paragraph_limit(style_instructions),
        'image_prompt': image_prompt or '',
        'image_mode': _normalize_image_mode(image_mode),
        'image_details': (image_details or '').strip(),
        'illustration_note': (illustration_meta or {}).get('note', ''),
        'illustration_meta': illustration_meta or {},
    }


def build_other_email_payload(
    selected_game_ids, prompt_style='default', custom_prompt='', image_mode='none',
    image_details='', illustration_players=None,
):
    from other_functions import readable_games_data, _is_valid_player_name
    from player_functions import get_player_by_name

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError('Gemini API key not configured.')

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

    context = f"Game Type: {game_name_label}\n\n"
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
        comment_str = f" - {comment}" if comment else ""
        context += f"- {winner_names} def. {loser_names}{score_str}{game_label}{comment_str}\n"

    style_instructions = _build_recap_style_instructions(prompt_style, context, custom_prompt)
    prompt = _build_recap_prompt(style_instructions, context)
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

    hero_image_url, hero_image_path, hero_image_error, image_prompt, illustration_meta = (
        _try_generate_email_hero_image(
            api_key, 'other', games, players_set, game_name=game_name_label,
            image_mode=image_mode,
            image_details=image_details,
            selected_players=illustration_players,
        )
    )
    html_body = create_other_email_html(
        summary, stats, games, date_obj, game_name_label,
        hero_image_url=hero_image_url,
    )
    plain_text_body = create_other_email_plain_text(
        summary, stats, games, date_obj, game_name_label,
    )
    subject = generate_ai_email_subject(summary, 'other', date_obj, game_name_label)

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
        'plain_text_body': plain_text_body,
        'subject': subject,
        'game_type': 'other',
        'hero_image_url': hero_image_url,
        'hero_image_path': hero_image_path,
        'hero_image_error': hero_image_error,
        'date_obj': date_obj,
        'formatted_date': formatted_date,
        'ai_prompt': prompt,
        'style_instructions': _strip_recap_paragraph_limit(style_instructions),
        'image_prompt': image_prompt or '',
        'image_mode': _normalize_image_mode(image_mode),
        'image_details': (image_details or '').strip(),
        'illustration_note': (illustration_meta or {}).get('note', ''),
        'illustration_meta': illustration_meta or {},
    }
