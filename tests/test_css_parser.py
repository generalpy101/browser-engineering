from pybrowser.css_parser import CSSParser, _to_px, resolve_color, sort_rules, style
from pybrowser.html_parser import Element, HTMLParser


class TestCSSParser:
    def test_tag_selector(self):
        rules = CSSParser("p { color: red; }").parse()
        assert len(rules) == 1
        sel, body = rules[0]
        assert body["color"] == "red"

    def test_class_selector(self):
        rules = CSSParser(".foo { margin: 10px; }").parse()
        sel, body = rules[0]
        assert "margin-top" in body

    def test_id_selector(self):
        rules = CSSParser("#bar { display: none; }").parse()
        sel, body = rules[0]
        assert body["display"] == "none"

    def test_comma_selectors(self):
        rules = CSSParser("h1, h2, h3 { font-weight: bold; }").parse()
        assert len(rules) == 3

    def test_descendant_selector(self):
        rules = CSSParser("div p { color: blue; }").parse()
        assert len(rules) == 1

    def test_comments_skipped(self):
        rules = CSSParser("/* comment */ p { color: red; }").parse()
        assert len(rules) == 1

    def test_at_rule_skipped(self):
        rules = CSSParser("@media screen { p { color: red; } } h1 { color: blue; }").parse()
        assert any(body.get("color") == "blue" for _, body in rules)


class TestShorthandExpansion:
    def test_margin_one_value(self):
        rules = CSSParser("p { margin: 10px; }").parse()
        _, body = rules[0]
        assert body["margin-top"] == "10px"
        assert body["margin-right"] == "10px"
        assert body["margin-bottom"] == "10px"
        assert body["margin-left"] == "10px"

    def test_margin_two_values(self):
        rules = CSSParser("p { margin: 5px 10px; }").parse()
        _, body = rules[0]
        assert body["margin-top"] == "5px"
        assert body["margin-right"] == "10px"
        assert body["margin-left"] == "10px"

    def test_padding_four_values(self):
        rules = CSSParser("p { padding: 1px 2px 3px 4px; }").parse()
        _, body = rules[0]
        assert body["padding-top"] == "1px"
        assert body["padding-right"] == "2px"
        assert body["padding-bottom"] == "3px"
        assert body["padding-left"] == "4px"

    def test_background_shorthand(self):
        rules = CSSParser("p { background: #eee; }").parse()
        _, body = rules[0]
        assert body.get("background-color") == "#eee"


class TestColorResolve:
    def test_hex3(self):
        assert resolve_color("#abc") == "#aabbcc"

    def test_hex6(self):
        assert resolve_color("#aabbcc") == "#aabbcc"

    def test_rgb(self):
        assert resolve_color("rgb(255, 0, 128)") == "#ff0080"

    def test_named(self):
        assert resolve_color("navy") == "#000080"

    def test_transparent(self):
        assert resolve_color("transparent") is None

    def test_var_rejected(self):
        assert resolve_color("var(--color)") is None

    def test_important_stripped(self):
        result = resolve_color("#abc !important")
        assert result == "#aabbcc"


class TestUnits:
    def test_px(self):
        assert _to_px("16px") == 16.0

    def test_em(self):
        assert _to_px("2em", 16) == 32.0

    def test_percent(self):
        assert _to_px("50%", 20) == 10.0

    def test_rem(self):
        assert _to_px("1rem") == 16.0

    def test_auto(self):
        assert _to_px("auto") == 0.0


class TestStyleResolution:
    def test_inheritance(self):
        dom = HTMLParser("<p><b>bold</b></p>").parse()
        rules = sort_rules(CSSParser("p { color: red; }").parse())
        style(dom, rules)
        b = None
        for c in dom.children:
            if isinstance(c, Element) and c.tag == "body":
                for cc in c.children:
                    if isinstance(cc, Element) and cc.tag == "p":
                        for ccc in cc.children:
                            if isinstance(ccc, Element) and ccc.tag == "b":
                                b = ccc
        assert b is not None
        assert b.style.get("color") == "#ff0000"
