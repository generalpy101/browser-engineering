from __future__ import annotations

import tkinter.font
from typing import List, Union


class DrawText:
    def __init__(
        self, x: float, y: float, text: str,
        font: tkinter.font.Font, color: str,
        node: object = None,
    ) -> None:
        self.top = y
        self.left = x
        self.right = x + font.measure(text)
        self.text = text
        self.font = font
        self.color = color
        self.node = node
        self.bottom = y + font.metrics("linespace")

    def execute(self, scroll: int, canvas: object) -> None:
        canvas.create_text(
            self.left, self.top - scroll,
            text=self.text, font=self.font, fill=self.color, anchor="nw",
        )


class DrawRect:
    def __init__(
        self, x1: float, y1: float, x2: float, y2: float, color: str,
        node: object = None,
    ) -> None:
        self.top = y1
        self.left = x1
        self.bottom = y2
        self.right = x2
        self.color = color
        self.node = node

    def execute(self, scroll: int, canvas: object) -> None:
        canvas.create_rectangle(
            self.left, self.top - scroll,
            self.right, self.bottom - scroll,
            width=0, fill=self.color,
        )


class DrawOutline:
    def __init__(self, x1: float, y1: float, x2: float, y2: float,
                 color: str, width: float = 1, node: object = None) -> None:
        self.top = y1
        self.left = x1
        self.bottom = y2
        self.right = x2
        self.color = color
        self.line_width = width
        self.node = node

    def execute(self, scroll: int, canvas: object) -> None:
        canvas.create_rectangle(
            self.left, self.top - scroll,
            self.right, self.bottom - scroll,
            outline=self.color, width=self.line_width,
        )


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
        self.line_width = width
        self.node = None

    def execute(self, scroll: int, canvas: object) -> None:
        canvas.create_line(
            self.x1, self.y1 - scroll,
            self.x2, self.y2 - scroll,
            fill=self.color, width=self.line_width,
        )


DisplayCommand = Union[DrawText, DrawRect, DrawOutline, DrawLine]


def paint_tree(layout_obj: object, display_list: List[DisplayCommand]) -> None:
    display_list.extend(layout_obj.paint())
    for child in layout_obj.children:
        paint_tree(child, display_list)
