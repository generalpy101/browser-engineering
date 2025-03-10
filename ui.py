import tkinter
from url import Url
from typing import List, Tuple

WIDTH, HEIGHT = 1200, 900
HSTEP, VSTEP = 12, 18
SCROLL_STEP = 100


class BrowserUI:
    def __init__(self) -> None:
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(self.window, width=WIDTH, height=HEIGHT)
        self.canvas.pack()
        self.scroll = 0
        self.window.bind("<Down>", self.scrolldown)
        self.window.bind("<Up>", self.scrollup)
        self._bind_mouse_wheel()

        self.display_list = []

    def _bind_mouse_wheel(self):
        """
        Bind mouse wheel to scroll
        Event passes the delta value of the wheel. Different OS may have different values
        Windows and Mac have opposite sign for the delta value
        Linux uses <Button-4> and <Button-5> events
        """
        # If the OS is Windows or Mac, bind the mouse wheel to scroll
        if self.window.tk.call("tk", "windowingsystem") == "win32":
            self.window.bind("<MouseWheel>", self._on_mouse_wheel)
        elif self.window.tk.call("tk", "windowingsystem") == "aqua":
            self.window.bind("<MouseWheel>", self._on_mouse_wheel)
        # If the OS is Linux, bind the mouse wheel to Button-4 and Button-5
        elif self.window.tk.call("tk", "windowingsystem") == "x11":
            self.window.bind("<Button-4>", self._on_linux_scroll)
            self.window.bind("<Button-5>", self._on_linux_scroll)

    def _on_mouse_wheel(self, event):
        self.scroll += event.delta
        self.draw_text()

    def _on_linux_scroll(self, event: tkinter.Event):
        if event.num == 4:
            self.scroll -= SCROLL_STEP
        elif event.num == 5:
            self.scroll += SCROLL_STEP
        self.draw_text()

    def draw_text(self):
        self.canvas.delete("all")
        for x, y, c in self.display_list:
            # [Optimiztion] Skip drawing if the text is outside the visible area
            if y > self.scroll + HEIGHT:
                continue
            if y + VSTEP < self.scroll:
                continue

            self.canvas.create_text(
                x, y - self.scroll, text=c, font=("Noto Sans CJK SC", 12)
            )

    def load(self, url) -> None:
        url = Url(url=url)
        html_content = url.get_html_text_content()
        self.compute_layout(html_content)
        self.draw_text()

    def compute_layout(self, content: str) -> None:
        self.display_list = []
        cursor_x, cursor_y = HSTEP, VSTEP
        for c in content:
            if c == "\n":
                cursor_y += VSTEP
                cursor_x = HSTEP
                continue
            self.display_list.append((cursor_x, cursor_y, c))
            cursor_x += HSTEP
            if cursor_x >= WIDTH - HSTEP:
                cursor_y += VSTEP
                cursor_x = HSTEP

    def scrolldown(self, e):
        self.scroll += SCROLL_STEP
        self.draw_text()

    def scrollup(self, e):
        self.scroll -= SCROLL_STEP
        self.draw_text()


if __name__ == "__main__":
    import sys

    BrowserUI().load(sys.argv[1])
    tkinter.mainloop()
