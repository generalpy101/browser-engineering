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


DisplayCommand = Union[DrawText, DrawRect, DrawOutline, DrawLine, DrawImage]


def paint_tree(layout_obj: object, display_list: List[DisplayCommand]) -> None:
    display_list.extend(layout_obj.paint())
    for child in layout_obj.children:
        paint_tree(child, display_list)
