"""<canvas> 2D rendering context exposed to JavaScript."""
from __future__ import annotations

from typing import Dict, List, Optional

from .renderer import SDLRenderer


class Canvas2D:
    """Stores draw commands from JS, replayed during paint."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.commands: List[tuple] = []
        self._fill_color = "#000000"
        self._stroke_color = "#000000"
        self._line_width = 1
        self._font_size = 16

    def clear(self) -> None:
        self.commands = []

    def execute(self, renderer: SDLRenderer, x: float, y: float, scroll: int) -> None:
        for cmd in self.commands:
            op = cmd[0]
            if op == "fillRect":
                _, rx, ry, rw, rh, color = cmd
                renderer.draw_rect(x + rx, y + ry - scroll, rw, rh, color)
            elif op == "strokeRect":
                _, rx, ry, rw, rh, color, lw = cmd
                renderer.draw_outline(x + rx, y + ry - scroll, rw, rh, color, int(lw))
            elif op == "fillText":
                _, text, tx, ty, color, size = cmd
                font = renderer.get_font(int(size), "normal", "roman", "Helvetica")
                renderer.draw_text(x + tx, y + ty - scroll, text, font, color)
            elif op == "line":
                _, x1, y1, x2, y2, color, lw = cmd
                renderer.draw_line(x + x1, y + y1 - scroll, x + x2, y + y2 - scroll, color, int(lw))
            elif op == "clearRect":
                _, rx, ry, rw, rh = cmd
                renderer.draw_rect(x + rx, y + ry - scroll, rw, rh, "#ffffff")


_canvases: Dict[int, Canvas2D] = {}
_next_id = 1


def create_canvas(width: int, height: int) -> int:
    global _next_id
    cid = _next_id
    _next_id += 1
    _canvases[cid] = Canvas2D(width, height)
    return cid


def get_canvas(cid: int) -> Optional[Canvas2D]:
    return _canvases.get(cid)


def canvas_fill_rect(cid: int, x: float, y: float, w: float, h: float, color: str) -> None:
    c = _canvases.get(cid)
    if c:
        c.commands.append(("fillRect", x, y, w, h, color))


def canvas_stroke_rect(cid: int, x: float, y: float, w: float, h: float,
                       color: str, lw: float) -> None:
    c = _canvases.get(cid)
    if c:
        c.commands.append(("strokeRect", x, y, w, h, color, lw))


def canvas_fill_text(cid: int, text: str, x: float, y: float,
                     color: str, size: float) -> None:
    c = _canvases.get(cid)
    if c:
        c.commands.append(("fillText", text, x, y, color, size))


def canvas_line(cid: int, x1: float, y1: float, x2: float, y2: float,
                color: str, lw: float) -> None:
    c = _canvases.get(cid)
    if c:
        c.commands.append(("line", x1, y1, x2, y2, color, lw))


def canvas_clear_rect(cid: int, x: float, y: float, w: float, h: float) -> None:
    c = _canvases.get(cid)
    if c:
        c.commands.append(("clearRect", x, y, w, h))


def canvas_clear(cid: int) -> None:
    c = _canvases.get(cid)
    if c:
        c.commands = []
