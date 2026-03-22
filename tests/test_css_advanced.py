"""Test advanced CSS features: _js_style overrides, color edge cases."""
from pybrowser.css_parser import CSSParser, resolve_color, sort_rules, style
from pybrowser.html_parser import Element, HTMLParser


class TestJsStyleOverride:
    def test_js_style_survives_restyle(self):
        dom = HTMLParser('<html><body><p id="t">Hi</p></body></html>').parse()
        rules = sort_rules(CSSParser("p { color: red; }").parse())
        style(dom, rules)

        # Find the <p> element
        def find(node, tag):
            if isinstance(node, Element) and node.tag == tag: return node
            if isinstance(node, Element):
                for c in node.children:
                    r = find(c, tag)
                    if r: return r
            return None

        p = find(dom, "p")
        p._js_style = {"color": "blue"}

        # Re-style -- _js_style should override cascade
        style(dom, rules)
        assert p.style.get("color") == "#0000ff"

    def test_js_style_empty(self):
        dom = HTMLParser('<html><body><p>Hi</p></body></html>').parse()
        rules = sort_rules(CSSParser("p { color: red; }").parse())
        style(dom, rules)
        p = None
        for el in dom.children:
            if isinstance(el, Element) and el.tag == "body":
                for c in el.children:
                    if isinstance(c, Element) and c.tag == "p":
                        p = c
        assert p.style.get("color") == "#ff0000"


class TestColorEdgeCases:
    def test_var_function(self):
        assert resolve_color("var(--main-color)") is None

    def test_important(self):
        assert resolve_color("#abc !important") == "#aabbcc"

    def test_currentcolor(self):
        assert resolve_color("currentcolor") is None

    def test_hex8(self):
        assert resolve_color("#aabbccdd") == "#aabbcc"

    def test_rgb_percent(self):
        r = resolve_color("rgb(100%, 0%, 50%)")
        assert r is not None

    def test_unknown_value(self):
        assert resolve_color("gradient(whatever)") is None

    def test_empty(self):
        assert resolve_color("") is None
        assert resolve_color("  ") is None
