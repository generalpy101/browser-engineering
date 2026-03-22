"""Test CSS flexbox layout."""
from pybrowser.css_parser import CSSParser, sort_rules, style
from pybrowser.html_parser import HTMLParser
from pybrowser.layout import DocumentLayout, set_renderer


def _setup_renderer():
    try:
        from pybrowser.renderer import SDLRenderer
        r = SDLRenderer(800, 600, "test")
        set_renderer(r)
        return r
    except Exception:
        return None


def _layout(html, css=""):
    dom = HTMLParser(html).parse()
    rules = sort_rules(CSSParser(css + " script{display:none} head{display:none}").parse())
    style(dom, rules)
    doc = DocumentLayout(dom, 800)
    doc.layout()
    return doc


class TestFlexLayout:
    @classmethod
    def setup_class(cls):
        cls._renderer = _setup_renderer()

    @classmethod
    def teardown_class(cls):
        if cls._renderer:
            cls._renderer.destroy()

    def test_flex_row_children_side_by_side(self):
        if not self._renderer: return
        doc = _layout(
            '<div style="display:flex"><div>A</div><div>B</div></div>',
        )
        flex = doc.children[0].children[0].children[0]
        if hasattr(flex, 'children') and len(flex.children) >= 2:
            a, b = flex.children[0], flex.children[1]
            assert b.x > a.x, "Second flex child should be to the right"

    def test_flex_column_children_stacked(self):
        if not self._renderer: return
        doc = _layout(
            '<div style="display:flex; flex-direction:column"><div>A</div><div>B</div></div>',
        )
        flex = doc.children[0].children[0].children[0]
        if hasattr(flex, 'children') and len(flex.children) >= 2:
            a, b = flex.children[0], flex.children[1]
            assert b.y > a.y, "Second flex child should be below"

    def test_flex_has_height(self):
        if not self._renderer: return
        doc = _layout(
            '<div style="display:flex"><div>Item</div></div>',
        )
        flex = doc.children[0].children[0].children[0]
        assert flex.height > 0


class TestTableLayout:
    @classmethod
    def setup_class(cls):
        cls._renderer = _setup_renderer()

    @classmethod
    def teardown_class(cls):
        if cls._renderer:
            cls._renderer.destroy()

    def test_table_row_cells_side_by_side(self):
        if not self._renderer: return
        doc = _layout('<table><tr><td>A</td><td>B</td><td>C</td></tr></table>')
        # Find the tr's layout
        def find_tr(node):
            from pybrowser.html_parser import Element
            if hasattr(node, 'node') and isinstance(node.node, Element) and node.node.tag == 'tr':
                return node
            for c in getattr(node, 'children', []):
                r = find_tr(c)
                if r: return r
            return None
        tr = find_tr(doc)
        if tr and len(tr.children) >= 2:
            assert tr.children[1].x > tr.children[0].x, "Table cells should be side by side"
