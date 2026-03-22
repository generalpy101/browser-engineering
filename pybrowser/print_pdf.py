"""Print page to PDF by rendering display list to an image, then saving as PDF."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    pass


def save_pdf(display_list: List, page_width: int, page_height: int,
             output_path: str, renderer: object) -> str:
    """Render the display list to a PDF file. Returns the output path."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return "Error: Pillow not installed"

    img = Image.new("RGB", (page_width, max(page_height, 100)), "white")
    draw = ImageDraw.Draw(img)

    for cmd in display_list:
        _draw_cmd(draw, cmd, 0)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path, "PDF")
    return output_path


def _draw_cmd(draw, cmd, scroll: int) -> None:
    from .paint import DrawLine, DrawOutline, DrawRect, DrawText

    if isinstance(cmd, DrawRect):
        try:
            draw.rectangle(
                [cmd.left, cmd.top - scroll, cmd.right, cmd.bottom - scroll],
                fill=cmd.color,
            )
        except Exception:
            pass
    elif isinstance(cmd, DrawOutline):
        try:
            draw.rectangle(
                [cmd.left, cmd.top - scroll, cmd.right, cmd.bottom - scroll],
                outline=cmd.color, width=cmd.line_width,
            )
        except Exception:
            pass
    elif isinstance(cmd, DrawLine):
        try:
            draw.line(
                [cmd.x1, cmd.y1 - scroll, cmd.x2, cmd.y2 - scroll],
                fill=cmd.color, width=cmd.line_width,
            )
        except Exception:
            pass
    elif isinstance(cmd, DrawText):
        if cmd.text and cmd.font:
            try:
                draw.text((cmd.left, cmd.top - scroll), cmd.text, fill=cmd.color)
            except Exception:
                pass
