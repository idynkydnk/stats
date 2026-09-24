"""Turn one twelve-pose contact sheet into a looping recap hero GIF."""

import io

from PIL import Image, ImageOps


SHEET_SIZE = '1536x1440'
FRAME_SIZE = (384, 480)


def animation_subject(details, players):
    """Read the selection from the saved prompt; older clients default to one player."""
    details = (details or '').strip()
    if details.startswith('Moving player: '):
        name, _, action = details[len('Moving player: '):].partition('\n')
        if name not in players:
            raise ValueError('Choose a player from these games who has a saved character or likeness.')
        return name, action.removeprefix('Action: ').strip() or 'Wave, then return to the starting pose.'
    if not players:
        raise ValueError('No player references are available for animation.')
    return players[0], details or 'Wave, then return to the starting pose.'


def animation_first_frame_prompt(scene_prompt, player):
    return f"""Create ONE portrait 4:5 starting frame for a one-person animation.
{scene_prompt}

MANDATORY COMPOSITION: {player} is the ONLY person who will move. Place their
entire body and any ball in the LEFT 40 percent of the picture. Leave empty
space from 40 to 50 percent across the picture. Place EVERY other person,
companion and pet entirely in the RIGHT half, with no overlap into the left.
Use a simple background and fixed camera. Keep the moving player's action
small and in place. No text or labels. These layout rules override other scene
composition instructions. Show the selected player in the action's starting pose.
"""


def animation_sheet_prompt(scene_prompt, action, player='the selected player'):
    return f"""Create ONE animation sprite sheet containing EXACTLY 12 frames.
Layout: 4 equal columns by 3 equal rows, edge to edge, NO gutters, borders,
frame numbers, captions, or text. Each cell is a complete portrait 4:5 frame.
Read frames left to right, then top to bottom.

The attached STARTING FRAME is authoritative. Cell 1 must reproduce it exactly.
Scene context: {scene_prompt}
ONLY MOVING PERSON: {player}.
Requested movement: {action or 'Wave, then return to the starting pose.'}

Only {player} and their ball, if needed, may move. If the action asks multiple
people to move, perform only the selected person's part. EVERY OTHER person,
companion, pet and object must remain frozen in the starting pose. Never add
another moving person. Keep the camera and background fixed. Keep {player}'s
entire body and any ball inside the LEFT 40 percent of EVERY frame. Preserve
the empty space between 40 and 50 percent and the stationary group on the right.
Draw 12 small consecutive pose changes for a short looping action in place.
Keep the same face and clothes throughout. The last pose flows into the first.
These layout and one-person rules override all other scene instructions.
"""


def animation_gif_from_sheet(image_bytes, first_frame_bytes=None):
    """Split row-major cells before fitting each frame; never crop the whole sheet."""
    with Image.open(io.BytesIO(image_bytes)) as source:
        sheet = ImageOps.exif_transpose(source).convert('RGB')
    width, height = sheet.size
    if width < 400 or height < 300:
        raise ValueError('Animation frame sheet is too small. Please try again.')
    # Production may have Pillow predating the Resampling/Dither enums.
    lanczos = getattr(Image, 'Resampling', Image).LANCZOS
    no_dither = getattr(Image, 'Dither', Image).NONE
    frames = []
    for row in range(3):
        for col in range(4):
            cell = sheet.crop((
                col * width // 4, row * height // 3,
                (col + 1) * width // 4, (row + 1) * height // 3,
            ))
            frames.append(ImageOps.fit(cell, FRAME_SIZE, method=lanczos))
    if first_frame_bytes:
        with Image.open(io.BytesIO(first_frame_bytes)) as source:
            first = ImageOps.fit(ImageOps.exif_transpose(source).convert('RGB'), FRAME_SIZE, method=lanczos)
        # Only the left action area is replaceable. Every other player is copied
        # from the original frame, never from the AI's subsequent redraws.
        from PIL import ImageDraw
        mask = Image.new('L', FRAME_SIZE, 0)
        draw = ImageDraw.Draw(mask)
        edge = int(FRAME_SIZE[0] * 0.45)
        draw.rectangle((0, 0, edge - 5, FRAME_SIZE[1]), fill=255)
        for x in range(edge - 4, edge):
            draw.line((x, 0, x, FRAME_SIZE[1]), fill=int(255 * (edge - x) / 5))
        frames = [first] + [Image.composite(frame, first, mask) for frame in frames[1:]]
    # Use the final composite colors for one palette throughout the loop.
    palette_sheet = Image.new('RGB', (FRAME_SIZE[0] * 4, FRAME_SIZE[1] * 3))
    for i, frame in enumerate(frames):
        palette_sheet.paste(frame, ((i % 4) * FRAME_SIZE[0], (i // 4) * FRAME_SIZE[1]))
    palette = palette_sheet.quantize(colors=256)
    frames = [frame.quantize(palette=palette, dither=no_dither) for frame in frames]
    output = io.BytesIO()
    frames[0].save(
        output, format='GIF', save_all=True, append_images=frames[1:],
        duration=160, loop=0, disposal=2, optimize=False,
    )
    return output.getvalue()
