"""Small, named season emblems for messaging previews; no stored user media."""
from datetime import date
from functools import lru_cache
from hashlib import sha256
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


def season_date(value):
    day = date.fromisoformat(value)
    return f'{day:%b} {day.day}, {day.year}'


def preview_version(season):
    content = '|'.join(season[key] for key in ('name', 'start_date', 'end_date'))
    return sha256(('season-arena-v1|' + content).encode()).hexdigest()[:12]


def _font(size):
    for path in ('DejaVuSans-Bold.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                 '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
                 '/System/Library/Fonts/Supplemental/Arial Bold.ttf'):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow 10.0; production normally supplies DejaVu.
        return ImageFont.load_default()


def _title_lines(draw, name, font, width=480):
    lines = ['']
    # Character wrapping also handles an 80-character name with no spaces.
    for word in name.split():
        candidate = (lines[-1] + ' ' + word).strip()
        if draw.textlength(candidate, font=font) <= width:
            lines[-1] = candidate
            continue
        if lines[-1]:
            lines.append('')
        for char in word:
            if lines[-1] and draw.textlength(lines[-1] + char, font=font) > width:
                lines.append('')
            lines[-1] += char
    return lines


@lru_cache(maxsize=64)
def season_share_image(name, start_date, end_date):
    """Return an opaque 600px PNG, legible as a square chat thumbnail."""
    image = Image.new('RGB', (600, 600), '#101c2a')
    draw = ImageDraw.Draw(image)
    gold, cream, muted = '#f3cd87', '#fff5df', '#b9c7d3'
    draw.rounded_rectangle((18, 18, 581, 581), radius=32, outline='#58616a', width=2)
    draw.text((300, 42), 'S E A S O N', font=_font(21), fill=gold, anchor='mt')
    # Floodlights and their beams echo the season's on-page court illustration.
    draw.polygon([(104, 120), (164, 120), (360, 292), (55, 292)], fill='#28343a')
    draw.polygon([(436, 120), (496, 120), (545, 292), (240, 292)], fill='#28343a')
    for x in (134, 466):
        draw.line((x, 123, x, 258), fill='#788995', width=5)
        draw.rounded_rectangle((x - 32, 102, x + 32, 130), radius=5, fill=gold)
        for offset in (-11, 11):
            draw.line((x + offset, 104, x + offset, 128), fill='#957c4d', width=2)
        draw.line((x - 30, 116, x + 30, 116), fill='#957c4d', width=2)
    draw.polygon([(175, 231), (425, 231), (495, 292), (105, 292)], fill='#1c303e', outline=gold, width=2)
    draw.line((300, 231, 300, 292), fill='#8e886d', width=2)
    draw.line((141, 260, 459, 260), fill='#8e886d', width=2)
    for x in (155, 445):
        draw.line((x, 195, x, 265), fill=cream, width=3)
    for y in (203, 214, 225, 236):
        draw.line((155, y, 445, y), fill='#83949b', width=1)
    for x in range(155, 446, 14):
        draw.line((x, 203, x, 236), fill='#83949b', width=1)
    draw.line((155, 203, 445, 203), fill=cream, width=3)
    draw.ellipse((284, 150, 316, 182), fill=cream)
    draw.arc((285, 150, 325, 186), 110, 240, fill='#a58d58', width=2)
    draw.line((286, 158, 311, 178), fill='#a58d58', width=2)
    draw.line((300, 95, 300, 111), fill=gold, width=2)
    draw.line((292, 103, 308, 103), fill=gold, width=2)

    for size in range(72, 21, -2):
        font = _font(size)
        lines = _title_lines(draw, name, font)
        line_height = size + 8
        if len(lines) * line_height <= 192:
            break
    top = 324 + (192 - len(lines) * line_height) / 2
    for i, line in enumerate(lines):
        draw.text((300, top + i * line_height), line, font=font, fill=cream, anchor='mt')
    dates = f'{season_date(start_date)} – {season_date(end_date)}'
    draw.text((300, 542), dates, font=_font(18), fill=muted, anchor='mm')
    output = BytesIO()
    image.save(output, format='PNG', optimize=True)
    return output.getvalue()
