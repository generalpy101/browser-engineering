"""SDL2 rendering backend -- window, GPU renderer, font management, text measurement."""
from __future__ import annotations

import ctypes
import os
import sys
from typing import Any, Dict, Tuple

import sdl2
import sdl2.ext
from sdl2 import sdlttf

# ---------------------------------------------------------------------------
# Font discovery
# ---------------------------------------------------------------------------

_FONT_SEARCH_DIRS = []
if sys.platform == "darwin":
    _FONT_SEARCH_DIRS = [
        "/System/Library/Fonts",
        "/System/Library/Fonts/Supplemental",
        "/Library/Fonts",
        os.path.expanduser("~/Library/Fonts"),
    ]
elif sys.platform == "win32":
    _FONT_SEARCH_DIRS = [os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")]
else:
    _FONT_SEARCH_DIRS = [
        "/usr/share/fonts/truetype",
        "/usr/share/fonts/TTF",
        "/usr/share/fonts",
        os.path.expanduser("~/.local/share/fonts"),
    ]

_FAMILY_MAP: Dict[str, str] = {}


def _build_font_map() -> None:
    if _FAMILY_MAP:
        return
    for d in _FONT_SEARCH_DIRS:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.lower().endswith((".ttf", ".otf", ".ttc")):
                    key = f.rsplit(".", 1)[0].lower().replace(" ", "")
                    _FAMILY_MAP[key] = os.path.join(root, f)


def _find_font_path(family: str, bold: bool = False, italic: bool = False) -> str:
    _build_font_map()
    family_clean = family.lower().replace(" ", "").replace("'", "").replace('"', "")
    for fam in family_clean.split(","):
        fam = fam.strip()
        if fam in ("serif", "times"):
            fam = "times"
        elif fam in ("sans-serif", "helvetica", "arial"):
            fam = "helvetica"
        elif fam in ("monospace", "courier"):
            fam = "courier"

        suffixes = []
        if bold and italic:
            suffixes = ["bolditalic", "boldit", "bi", "bold", ""]
        elif bold:
            suffixes = ["bold", "b", ""]
        elif italic:
            suffixes = ["italic", "it", "oblique", "i", ""]
        else:
            suffixes = ["regular", "roman", "r", ""]

        for suffix in suffixes:
            candidate = fam + suffix
            if candidate in _FAMILY_MAP:
                return _FAMILY_MAP[candidate]

        candidates = [(k, v) for k, v in _FAMILY_MAP.items() if fam in k]
        candidates.sort(key=lambda kv: len(kv[0]))
        for key, path in candidates:
            if "bold" not in key and "italic" not in key and "oblique" not in key:
                return path
        for key, path in candidates:
            return path

    for fallback in ["helvetica", "arial", "dejavusans", "liberationsans"]:
        if fallback in _FAMILY_MAP:
            return _FAMILY_MAP[fallback]

    for _, path in sorted(_FAMILY_MAP.items()):
        return path

    raise RuntimeError("No fonts found on system")


# ---------------------------------------------------------------------------
# Font wrapper (same interface as old tkinter.font.Font)
# ---------------------------------------------------------------------------

class Font:
    def __init__(self, sdl_font: Any, size: int) -> None:
        self._font = sdl_font
        self._size = size
        self._ascent = sdlttf.TTF_FontAscent(sdl_font)
        self._descent = abs(sdlttf.TTF_FontDescent(sdl_font))
        self._height = sdlttf.TTF_FontHeight(sdl_font)
        self._linespace = sdlttf.TTF_FontLineSkip(sdl_font)

    def measure(self, text: str) -> int:
        if not text:
            return 0
        w = ctypes.c_int(0)
        h = ctypes.c_int(0)
        sdlttf.TTF_SizeUTF8(self._font, text.encode("utf-8"), ctypes.byref(w), ctypes.byref(h))
        return w.value

    def metrics(self, key: str) -> int:
        if key == "ascent":
            return self._ascent
        if key == "descent":
            return self._descent
        if key == "linespace":
            return self._linespace
        return self._height


# ---------------------------------------------------------------------------
# SDL2 Renderer
# ---------------------------------------------------------------------------

class SDLRenderer:
    def __init__(self, width: int, height: int, title: str = "Pybrowser") -> None:
        sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO)
        sdlttf.TTF_Init()
        sdl2.SDL_StartTextInput()

        self._window = sdl2.SDL_CreateWindow(
            title.encode("utf-8"),
            sdl2.SDL_WINDOWPOS_CENTERED, sdl2.SDL_WINDOWPOS_CENTERED,
            width, height,
            sdl2.SDL_WINDOW_SHOWN | sdl2.SDL_WINDOW_RESIZABLE,
        )
        self._renderer = sdl2.SDL_CreateRenderer(
            self._window, -1,
            sdl2.SDL_RENDERER_ACCELERATED | sdl2.SDL_RENDERER_PRESENTVSYNC,
        )
        self.width = width
        self.height = height

        self._font_cache: Dict[Tuple, Font] = {}
        self._ttf_cache: Dict[Tuple, Any] = {}
        self._texture_cache: Dict[int, Any] = {}

    def destroy(self) -> None:
        for tex in self._texture_cache.values():
            if tex:
                sdl2.SDL_DestroyTexture(tex)
        for ttf in self._ttf_cache.values():
            if ttf:
                sdlttf.TTF_CloseFont(ttf)
        sdl2.SDL_DestroyRenderer(self._renderer)
        sdl2.SDL_DestroyWindow(self._window)
        sdlttf.TTF_Quit()
        sdl2.SDL_Quit()

    def set_title(self, title: str) -> None:
        sdl2.SDL_SetWindowTitle(self._window, title.encode("utf-8"))

    def get_size(self) -> Tuple[int, int]:
        w = ctypes.c_int(0)
        h = ctypes.c_int(0)
        sdl2.SDL_GetWindowSize(self._window, ctypes.byref(w), ctypes.byref(h))
        self.width = w.value
        self.height = h.value
        return w.value, h.value

    # -- font management ----------------------------------------------------

    def get_font(self, size: int, weight: str, slant: str, family: str) -> Font:
        key = (size, weight, slant, family)
        if key in self._font_cache:
            return self._font_cache[key]
        bold = weight == "bold"
        italic = slant == "italic"
        path = _find_font_path(family, bold, italic)
        ttf_key = (path, size)
        if ttf_key not in self._ttf_cache:
            ttf = sdlttf.TTF_OpenFont(path.encode("utf-8"), size)
            if not ttf:
                raise RuntimeError(f"Failed to open font: {path} size={size}")
            self._ttf_cache[ttf_key] = ttf
        font = Font(self._ttf_cache[ttf_key], size)
        self._font_cache[key] = font
        return font

    # -- drawing primitives -------------------------------------------------

    def clear(self, color: str) -> None:
        r, g, b = _parse_color(color)
        sdl2.SDL_SetRenderDrawColor(self._renderer, r, g, b, 255)
        sdl2.SDL_RenderClear(self._renderer)

    def draw_rect(self, x: float, y: float, w: float, h: float, color: str) -> None:
        r, g, b = _parse_color(color)
        sdl2.SDL_SetRenderDrawColor(self._renderer, r, g, b, 255)
        rect = sdl2.SDL_Rect(int(x), int(y), int(w), int(h))
        sdl2.SDL_RenderFillRect(self._renderer, rect)

    def draw_outline(self, x: float, y: float, w: float, h: float,
                     color: str, line_width: int = 1) -> None:
        r, g, b = _parse_color(color)
        sdl2.SDL_SetRenderDrawColor(self._renderer, r, g, b, 255)
        for i in range(line_width):
            rect = sdl2.SDL_Rect(int(x) + i, int(y) + i, int(w) - 2 * i, int(h) - 2 * i)
            sdl2.SDL_RenderDrawRect(self._renderer, rect)

    def draw_line(self, x1: float, y1: float, x2: float, y2: float,
                  color: str, width: int = 1) -> None:
        r, g, b = _parse_color(color)
        sdl2.SDL_SetRenderDrawColor(self._renderer, r, g, b, 255)
        sdl2.SDL_RenderDrawLine(self._renderer, int(x1), int(y1), int(x2), int(y2))

    def draw_text(self, x: float, y: float, text: str, font: Font, color: str) -> None:
        if not text:
            return
        r, g, b = _parse_color(color)
        key = (id(font._font), text, r, g, b)
        if key not in self._texture_cache:
            sdl_color = sdl2.SDL_Color(r, g, b, 255)
            surface = sdlttf.TTF_RenderUTF8_Blended(
                font._font, text.encode("utf-8"), sdl_color,
            )
            if not surface:
                return
            texture = sdl2.SDL_CreateTextureFromSurface(self._renderer, surface)
            sdl2.SDL_FreeSurface(surface)
            self._texture_cache[key] = texture
        texture = self._texture_cache[key]
        if not texture:
            return
        tw = ctypes.c_int(0)
        th = ctypes.c_int(0)
        sdl2.SDL_QueryTexture(texture, None, None, ctypes.byref(tw), ctypes.byref(th))
        dst = sdl2.SDL_Rect(int(x), int(y), tw.value, th.value)
        sdl2.SDL_RenderCopy(self._renderer, texture, None, dst)

    def draw_image(self, x: float, y: float, w: float, h: float,
                   image_data: bytes) -> None:
        key = hash(image_data[:256]) if image_data else 0
        if key not in self._texture_cache:
            try:
                import io

                from PIL import Image
                img = Image.open(io.BytesIO(image_data)).convert("RGBA")
                pixels = img.tobytes()
                surface = sdl2.SDL_CreateRGBSurfaceFrom(
                    pixels, img.width, img.height, 32, img.width * 4,
                    0x000000FF, 0x0000FF00, 0x00FF0000, 0xFF000000,
                )
                texture = sdl2.SDL_CreateTextureFromSurface(self._renderer, surface)
                sdl2.SDL_FreeSurface(surface)
                self._texture_cache[key] = (texture, img.width, img.height)
            except Exception:
                self._texture_cache[key] = None
        entry = self._texture_cache.get(key)
        if entry and isinstance(entry, tuple):
            texture, _, _ = entry
            dst = sdl2.SDL_Rect(int(x), int(y), int(w), int(h))
            sdl2.SDL_RenderCopy(self._renderer, texture, None, dst)

    def present(self) -> None:
        sdl2.SDL_RenderPresent(self._renderer)

    def flush_text_cache(self) -> None:
        for key, tex in list(self._texture_cache.items()):
            if isinstance(tex, tuple):
                continue
            if tex:
                sdl2.SDL_DestroyTexture(tex)
        self._texture_cache = {
            k: v for k, v in self._texture_cache.items() if isinstance(v, tuple)
        }

    # -- events -------------------------------------------------------------

    def poll_events(self) -> list:
        events = []
        event = sdl2.SDL_Event()
        while sdl2.SDL_PollEvent(ctypes.byref(event)):
            e = event
            if e.type == sdl2.SDL_QUIT:
                events.append({"type": "quit"})
            elif e.type == sdl2.SDL_MOUSEBUTTONDOWN:
                events.append({"type": "click", "x": e.button.x, "y": e.button.y,
                               "button": e.button.button})
            elif e.type == sdl2.SDL_MOUSEMOTION:
                events.append({"type": "motion", "x": e.motion.x, "y": e.motion.y})
            elif e.type == sdl2.SDL_MOUSEWHEEL:
                events.append({"type": "scroll", "y": e.wheel.y})
            elif e.type == sdl2.SDL_KEYDOWN:
                sym = e.key.keysym.sym
                mod = e.key.keysym.mod
                events.append({"type": "keydown", "sym": sym, "mod": mod,
                               "name": sdl2.SDL_GetKeyName(sym).decode()})
            elif e.type == sdl2.SDL_TEXTINPUT:
                text = e.text.text.decode("utf-8")
                events.append({"type": "textinput", "text": text})
            elif e.type == sdl2.SDL_WINDOWEVENT:
                if e.window.event == sdl2.SDL_WINDOWEVENT_RESIZED:
                    events.append({"type": "resize",
                                   "w": e.window.data1, "h": e.window.data2})
        return events


# ---------------------------------------------------------------------------
# Color parsing
# ---------------------------------------------------------------------------

_COLOR_CACHE: Dict[str, Tuple[int, int, int]] = {}


def _parse_color(color: str) -> Tuple[int, int, int]:
    if color in _COLOR_CACHE:
        return _COLOR_CACHE[color]

    result = (0, 0, 0)
    c = color.strip().lower()

    if c.startswith("#") and len(c) == 7:
        result = (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))
    elif c.startswith("#") and len(c) == 4:
        result = (int(c[1]*2, 16), int(c[2]*2, 16), int(c[3]*2, 16))
    elif c == "white":
        result = (255, 255, 255)
    elif c == "black":
        result = (0, 0, 0)
    elif c == "red":
        result = (255, 0, 0)
    elif c == "blue":
        result = (0, 0, 255)
    elif c == "green":
        result = (0, 128, 0)
    elif c == "gray" or c == "grey":
        result = (128, 128, 128)
    else:
        try:
            if c.startswith("#"):
                h = c[1:]
                result = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except (ValueError, IndexError):
            pass

    _COLOR_CACHE[color] = result
    return result
