# Pybrowser

A toy web browser built from scratch in Python, inspired by [Web Browser Engineering](https://browser.engineering/).

Every component is hand-written: HTTP client, HTML parser, CSS engine, layout engine, paint system, and a pluggable JavaScript runtime with a custom interpreter.

## Quick start

```bash
pip install -r requirements.txt   # optional: quickjs, dukpy
python -m pybrowser               # opens https://browser.engineering/
python -m pybrowser https://example.com
```

## Features

### Networking (`url.py`)
- Raw socket HTTP/HTTPS with TLS
- Redirect following (301/302/303)
- URL resolution (relative, absolute, fragment)
- Response caching
- `view-source:` scheme

### HTML (`html_parser.py`)
- State-machine tokenizer
- DOM tree with `Element` and `Text` nodes
- Attribute parsing, self-closing tags
- Implicit `<html>`, `<head>`, `<body>` insertion
- HTML entity decoding (`&amp;`, `&#123;`, `&#x1F;`)

### CSS (`css_parser.py`)
- Selectors: tag, `.class`, `#id`, descendant, `*`
- Comma-separated selectors (`h1, h2 { ... }`)
- Shorthand expansion (`margin`, `padding`, `background`, `border`, `font`)
- Relative units (`em`, `rem`, `%`, `ex`, `ch`, `pt`)
- Color normalization (`#RGB` -> `#RRGGBB`, `rgb()`, `rgba()`, named colors)
- Specificity-based cascade
- Style inheritance
- `@media` / `@import` skipping

### Layout (`layout.py`)
- Block and inline layout modes
- Anonymous block boxes for mixed content
- Margin collapsing between siblings
- `margin: auto` centering
- `max-width` support
- `text-align` (left, center, right)
- Font metrics via tkinter
- `<input>`, `<button>` widget rendering

### Paint (`paint.py`)
- Display list with `DrawText`, `DrawRect`, `DrawOutline`, `DrawLine`
- Viewport culling (only paint visible items)

### JavaScript (pluggable)

Three interchangeable engines:

| Engine | JS Version | Install | Flag |
|---|---|---|---|
| **QuickJS** | ES2020+ | `pip install quickjs` | `--quickjs` |
| **Dukpy** | ES5 | `pip install dukpy` | `--dukpy` |
| **ToyJS** | ES5 subset | built-in | `--toy` |

```bash
python -m pybrowser --quickjs https://example.com   # modern JS
python -m pybrowser --toy https://example.com        # custom interpreter
```

Auto-detection picks the best available (QuickJS > Dukpy > ToyJS).

#### Custom JS interpreter (`js_interpreter.py`)
Hand-written lexer, recursive-descent parser, and tree-walking evaluator supporting:
- Variables, functions, closures, arrow functions
- Objects, arrays, string/array methods
- Control flow (`if`/`else`, `while`, `for`, `try`/`catch`)
- Operators, type coercion, ternary, `typeof`

#### DOM bridge (`js_runtime.py`)
- `document.getElementById`, `querySelector`, `querySelectorAll`
- `document.createElement`, `createTextNode`
- `node.textContent`, `innerHTML`, `setAttribute`, `classList`
- `node.appendChild`, `removeChild`
- `node.addEventListener` with click event bubbling
- `node.style` read/write

#### Web APIs (`js_runtime.py`)
- `fetch(url)` with `.then()`, `.text()`, `.json()`
- `XMLHttpRequest`
- `localStorage` / `sessionStorage`
- `location`, `navigator`
- `console.log` / `alert`
- `setTimeout` / `setInterval`
- `encodeURIComponent` / `btoa` / `atob`

### Browser chrome (`browser.py`)
- Address bar with navigation
- Back/forward buttons with history
- Mouse wheel + keyboard scrolling
- Scrollbar indicator
- Click-to-focus text inputs
- Keyboard input with cursor
- Checkbox/radio toggle
- Form submission (GET with query string)
- Link hover cursor
- Loading indicator
- Window resize re-layout
- Body background color from CSS

## Architecture

```
URL fetch  ->  HTML parser  ->  CSS parser + cascade
                    |                   |
                    v                   v
                DOM tree  <---  Style resolution
                    |
                    v
             Layout engine  ->  Paint commands  ->  tkinter canvas
                    ^
                    |
              JS runtime  <---  Event dispatch
```

## File structure

```
pybrowser/
  __init__.py          Package marker
  __main__.py          Entry point (python -m pybrowser)
  browser.py           Browser shell, tkinter UI, event handling
  url.py               HTTP client, URL parsing, caching
  html_parser.py       HTML tokenizer and DOM tree builder
  css_parser.py        CSS parser, selectors, cascade, style resolution
  layout.py            Block/inline layout engine
  paint.py             Display list commands
  js/
    __init__.py        JS subpackage exports
    engine.py          Pluggable JS engine interface
    interpreter.py     Custom toy JS interpreter
    runtime.py         DOM bridge, Web APIs, event system
tests/
  test_url.py          URL parsing and resolution tests
  test_html_parser.py  HTML parser tests
  test_css_parser.py   CSS parser, cascade, color, unit tests
  test_js_interpreter.py  JS interpreter tests
  test_js_engine.py    Engine interface tests
  test_js_runtime.py   DOM bridge and event tests
```

## Development

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install ruff pytest

# Run tests
python -m pytest tests/ -v

# Lint
ruff check pybrowser/ tests/

# Auto-fix lint issues
ruff check --fix pybrowser/ tests/
```

CI runs lint + tests on every push and PR via GitHub Actions.

## Limitations

This is a learning project. It does not support:
- Images (`<img>` renders as placeholder)
- Flexbox / Grid layout
- CSS animations or transitions
- Web fonts
- `<iframe>`, `<canvas>`, `<video>`
- ES6 modules (`import`/`export`)
- Service workers, WebSockets
- CORS enforcement

## License

MIT
