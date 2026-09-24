"""Turn one twelve-pose contact sheet into a looping recap hero GIF."""

import io

from PIL import Image, ImageOps


SHEET_SIZE = '1536x1440'
FRAME_SIZE = (384, 480)


def animation_sheet_prompt(scene_prompt, action):
    return f"""Create ONE animation sprite sheet containing EXACTLY 12 frames.
Layout is mandatory: 4 equal columns by 3 equal rows, edge to edge, with NO
gutters, borders, panel numbers, captions, or text. Each cell is a complete
portrait 4:5 frame. Read frames left to right, then top to bottom.

Use the attached player references and these scene details in EVERY frame:
{scene_prompt}

Requested movement: {action or 'The players celebrate together, then return to their starting poses.'}

Animate one simple continuous action over the 12 consecutive poses. Keep the
same players, faces, clothing, companions, objects, background, camera position,
scale, and lighting across all cells. Only the action should change. Keep every
player fully inside each cell. Show small, readable changes from frame to frame.
The final pose should flow naturally back into the first pose for a repeating
loop. Do not repeat the same still image twelve times. These animation layout
rules take precedence over any single-picture layout or text-label instructions
in the scene details. Draw all 12 cells, not one large scene.
"""


def animation_gif_from_sheet(image_bytes):
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
    # One palette across the sequence reduces color flicker between frames.
    palette = sheet.quantize(colors=256)
    frames = [frame.quantize(palette=palette, dither=no_dither) for frame in frames]
    output = io.BytesIO()
    frames[0].save(
        output, format='GIF', save_all=True, append_images=frames[1:],
        duration=160, loop=0, disposal=2, optimize=False,
    )
    return output.getvalue()
