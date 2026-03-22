"""Display list commands for the paint phase."""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Union

if TYPE_CHECKING:
    from .renderer import Font, SDLRenderer


class DrawText:
    def __init__(self, x: float, y: float, text: str,
                 font: Font, color: str, node: object = None) -> None:
        self.top = y
        self.left = x
        self.text = text
        self.font = font
        self.color = color
        self.node = node
        self.right = x + (font.measure(text) if font else 0)
        self.bottom = y + (font.metrics("linespace") if font else 0)

    def execute(self, scroll: int, renderer: SDLRenderer) -> None:
        if self.font and self.text:
            renderer.draw_text(self.left, self.top - scroll, self.text, self.font, self.color)


class DrawRect:
    def __init__(self, x1: float, y1: float, x2: float, y2: float,
                 color: str, node: object = None) -> None:
        self.top = y1
        self.left = x1
        self.bottom = y2
        self.right = x2
        self.color = color
        self.node = node

    def execute(self, scroll: int, renderer: SDLRenderer) -> None:
        renderer.draw_rect(self.left, self.top - scroll,
                           self.right - self.left, self.bottom - self.top, self.color)


class DrawOutline:
    def __init__(self, x1: float, y1: float, x2: float, y2: float,
                 color: str, width: float = 1, node: object = None) -> None:
        self.top = y1
        self.left = x1
        self.bottom = y2
        self.right = x2
        self.color = color
        self.line_width = int(width)
        self.node = node

    def execute(self, scroll: int, renderer: SDLRenderer) -> None:
        renderer.draw_outline(self.left, self.top - scroll,
                              self.right - self.left, self.bottom - self.top,
                              self.color, self.line_width)


class DrawLine:
    def __init__(self, x1: float, y1: float, x2: float, y2: float,
                 color: str, width: float = 1) -> None:
        self.top = min(y1, y2)
        self.left = min(x1, x2)
        self.bottom = max(y1, y2) + width
        self.right = max(x1, x2)
        self.color = color
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.line_width = int(width)
        self.node = None

    def execute(self, scroll: int, renderer: SDLRenderer) -> None:
        renderer.draw_line(self.x1, self.y1 - scroll,
                           self.x2, self.y2 - scroll,
                           self.color, self.line_width)


class DrawImage:
    def __init__(self, x: float, y: float, width: float, height: float,
                 image_data: object, node: object = None) -> None:
        self.top = y
        self.left = x
        self.right = x + width
        self.bottom = y + height
        self.image_data = image_data
        self.node = node

    def execute(self, scroll: int, renderer: SDLRenderer) -> None:
        if self.image_data:
            renderer.draw_image(self.left, self.top - scroll,
                                self.right - self.left, self.bottom - self.top,
                                self.image_data)


class DrawRoundedRect:
    def __init__(self, x1: float, y1: float, x2: float, y2: float,
                 color: str, radius: int = 0, alpha: int = 255, node: object = None) -> None:
        self.top = y1
        self.left = x1
        self.bottom = y2
        self.right = x2
        self.color = color
        self.radius = radius
        self.alpha = alpha
        self.node = node

    def execute(self, scroll: int, renderer: SDLRenderer) -> None:
        renderer.draw_rounded_rect(
            self.left, self.top - scroll,
            self.right - self.left, self.bottom - self.top,
            self.color, self.radius, self.alpha,
        )


class DrawBoxShadow:
    def __init__(self, x1: float, y1: float, x2: float, y2: float,
                 color: str, blur: int = 4, spread: int = 0,
                 offset_x: int = 0, offset_y: int = 2) -> None:
        self.top = y1 + offset_y - blur - spread
        self.left = x1 + offset_x - blur - spread
        self.bottom = y2 + offset_y + blur + spread
        self.right = x2 + offset_x + blur + spread
        self.color = color
        self.blur = blur
        self.spread = spread
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.box = (x1, y1, x2, y2)
        self.node = None

    def execute(self, scroll: int, renderer: SDLRenderer) -> None:
        x1, y1, x2, y2 = self.box
        for i in range(self.blur, 0, -1):
            alpha = int(40 * (1 - i / self.blur))
            renderer.draw_rect(
                x1 + self.offset_x - i - self.spread,
                y1 + self.offset_y - i - self.spread - scroll,
                (x2 - x1) + 2 * (i + self.spread),
                (y2 - y1) + 2 * (i + self.spread),
                self.color, alpha,
            )


class ClipStart:
    def __init__(self, x: float, y: float, w: float, h: float) -> None:
        self.top = y
        self.left = x
        self.bottom = y + h
        self.right = x + w
        self.node = None
        self._rect = (x, y, w, h)

    def execute(self, scroll: int, renderer: SDLRenderer) -> None:
        import sdl2 as _sdl2
        x, y, w, h = self._rect
        _sdl2.SDL_RenderSetClipRect(
            renderer._renderer,
            _sdl2.SDL_Rect(int(x), int(y - scroll), int(w), int(h)),
        )


class ClipEnd:
    def __init__(self) -> None:
        self.top = self.left = self.bottom = self.right = 0
        self.node = None

    def execute(self, scroll: int, renderer: SDLRenderer) -> None:
        import sdl2 as _sdl2
        _sdl2.SDL_RenderSetClipRect(renderer._renderer, None)


class DrawCanvas:
    def __init__(self, x: float, y: float, w: float, h: float,
                 canvas_id: int, node: object = None) -> None:
        self.top = y
        self.left = x
        self.right = x + w
        self.bottom = y + h
        self.canvas_id = canvas_id
        self.node = node

    def execute(self, scroll: int, renderer: SDLRenderer) -> None:
        from .canvas2d import get_canvas
        c = get_canvas(self.canvas_id)
        if c:
            c.execute(renderer, self.left, self.top, scroll)


DisplayCommand = Union[DrawText, DrawRect, DrawOutline, DrawLine, DrawImage,
                       DrawRoundedRect, DrawBoxShadow, ClipStart, ClipEnd, DrawCanvas]


def paint_tree(layout_obj: object, display_list: List[DisplayCommand]) -> None:
    display_list.extend(layout_obj.paint())
    for child in layout_obj.children:
        paint_tree(child, display_list)
    post = getattr(layout_obj, "paint_post", None)
    if post:
        display_list.extend(post())
