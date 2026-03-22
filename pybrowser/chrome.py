"""Browser chrome drawing: tab bar, address bar, navigation buttons."""
from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .renderer import SDLRenderer
    from .tab import Tab

TAB_BAR_HEIGHT = 26
CHROME_HEIGHT = 60


def draw_chrome(
    renderer: SDLRenderer,
    font: object,
    tabs: List[Tab],
    active_tab: int,
    width: int,
    address_text: str,
    address_focused: bool,
    address_cursor: int,
    is_bookmarked: bool,
    tab_url: str,
) -> None:
    r = renderer
    f = font

    r.draw_rect(0, 0, width, CHROME_HEIGHT, "#e0e0e0")
    r.draw_line(0, CHROME_HEIGHT, width, CHROME_HEIGHT, "#bbbbbb", 1)

    # -- tab bar --
    tx = 4
    for i, t in enumerate(tabs):
        tw = min(160, max(80, f.measure(t.title[:18]) + 20))
        active = i == active_tab
        bg = "#ffffff" if active else "#d0d0d0"
        r.draw_rect(tx, 2, tw, TAB_BAR_HEIGHT - 2, bg)
        r.draw_outline(tx, 2, tw, TAB_BAR_HEIGHT - 2, "#aaaaaa")
        label = t.title[:18] + ("..." if len(t.title) > 18 else "")
        r.draw_text(tx + 6, 6, label, f, "#333333")
        r.draw_text(tx + tw - 16, 5, "x", f, "#999999")
        tx += tw + 2

    r.draw_rect(tx + 2, 4, 22, 18, "#d8d8d8")
    r.draw_text(tx + 7, 5, "+", f, "#666666")

    # -- address bar row --
    ay = TAB_BAR_HEIGHT + 2
    btn_w, btn_h = 26, 22

    # Back arrow
    r.draw_rect(4, ay, btn_w, btn_h, "#d0d0d0")
    r.draw_outline(4, ay, btn_w, btn_h, "#aaaaaa")
    ax, amid = 17, ay + btn_h // 2
    r.draw_line(ax, amid, ax - 7, amid, "#555555", 2)
    r.draw_line(ax - 7, amid, ax - 3, amid - 4, "#555555", 2)
    r.draw_line(ax - 7, amid, ax - 3, amid + 4, "#555555", 2)

    # Forward arrow
    r.draw_rect(34, ay, btn_w, btn_h, "#d0d0d0")
    r.draw_outline(34, ay, btn_w, btn_h, "#aaaaaa")
    ax2 = 43
    r.draw_line(ax2, amid, ax2 + 7, amid, "#555555", 2)
    r.draw_line(ax2 + 7, amid, ax2 + 3, amid - 4, "#555555", 2)
    r.draw_line(ax2 + 7, amid, ax2 + 3, amid + 4, "#555555", 2)

    # Bookmark star
    r.draw_rect(64, ay, btn_w, btn_h, "#d0d0d0")
    r.draw_outline(64, ay, btn_w, btn_h, "#aaaaaa")
    sx, sy = 77, ay + 5
    star_color = "#f1c40f" if is_bookmarked else "#aaaaaa"
    r.draw_line(sx, sy, sx - 4, sy + 12, star_color, 2)
    r.draw_line(sx, sy, sx + 4, sy + 12, star_color, 2)
    r.draw_line(sx - 6, sy + 5, sx + 6, sy + 5, star_color, 2)
    r.draw_line(sx - 6, sy + 5, sx + 3, sy + 12, star_color, 2)
    r.draw_line(sx + 6, sy + 5, sx - 3, sy + 12, star_color, 2)

    # Address bar
    addr_x = 96
    addr_w = width - addr_x - 8
    border = "#4488ff" if address_focused else "#bbbbbb"
    r.draw_rect(addr_x, ay, addr_w, btn_h, "#ffffff")
    r.draw_outline(addr_x, ay, addr_w, btn_h, border, 1)

    # HTTPS lock / HTTP warning
    is_secure = tab_url.startswith("https://")
    text_offset = addr_x + 6
    if is_secure:
        lx, ly = addr_x + 8, ay + 4
        r.draw_rect(lx, ly + 4, 8, 6, "#27ae60")
        r.draw_outline(lx + 1, ly, 6, 5, "#27ae60", 1)
        text_offset = addr_x + 20
    elif tab_url and not tab_url.startswith("pybrowser://"):
        r.draw_text(addr_x + 6, ay + 4, "!", f, "#e74c3c")
        text_offset = addr_x + 18

    r.draw_text(text_offset, ay + 4, address_text, f, "#333333")
    if address_focused:
        cx = addr_x + 6 + f.measure(address_text[:address_cursor])
        r.draw_line(cx, ay + 3, cx, ay + btn_h - 3, "#333333", 1)
