from pybrowser.css_parser import CSSParser, sort_rules, style
from pybrowser.html_parser import Element, HTMLParser, Text
from pybrowser.js import JSRuntime, ToyJSEngine


def make_dom(html):
    dom = HTMLParser(html).parse()
    rules = sort_rules(CSSParser("script { display: none; }").parse())
    style(dom, rules)
    return dom


def find(node, tag, id_val):
    if isinstance(node, Element) and node.tag == tag and node.attributes.get("id") == id_val:
        return node
    if isinstance(node, Element):
        for c in node.children:
            r = find(c, tag, id_val)
            if r:
                return r
    return None


class TestScriptExecution:
    def test_console_log(self):
        dom = make_dom('<html><body><script>console.log("hello");</script></body></html>')
        logs = []
        rt = JSRuntime(dom, engine=ToyJSEngine(), on_log=lambda *a: logs.append(" ".join(a)))
        rt.run_scripts(dom)
        assert logs == ["hello"]

    def test_get_element_by_id(self):
        dom = make_dom("""<html><body>
        <h1 id="title">Hello</h1>
        <script>
        var t = document.getElementById("title");
        console.log(t.textContent);
        </script></body></html>""")
        logs = []
        rt = JSRuntime(dom, engine=ToyJSEngine(), on_log=lambda *a: logs.append(" ".join(a)))
        rt.run_scripts(dom)
        assert logs == ["Hello"]


class TestEventHandling:
    def test_click_handler(self):
        dom = make_dom("""<html><body>
        <button id="btn">Click</button>
        <script>
        var count = 0;
        document.getElementById("btn").addEventListener("click", function() {
            count = count + 1;
            console.log("click " + count);
        });
        </script></body></html>""")
        logs = []
        rt = JSRuntime(dom, engine=ToyJSEngine(), on_log=lambda *a: logs.append(" ".join(a)))
        rt.run_scripts(dom)
        btn = find(dom, "button", "btn")
        rt.dispatch_click(btn)
        rt.dispatch_click(btn)
        assert logs == ["click 1", "click 2"]

    def test_event_bubbles(self):
        dom = make_dom("""<html><body>
        <div id="outer"><button id="inner">X</button></div>
        <script>
        document.getElementById("outer").addEventListener("click", function() {
            console.log("outer");
        });
        document.getElementById("inner").addEventListener("click", function() {
            console.log("inner");
        });
        </script></body></html>""")
        logs = []
        rt = JSRuntime(dom, engine=ToyJSEngine(), on_log=lambda *a: logs.append(" ".join(a)))
        rt.run_scripts(dom)
        btn = find(dom, "button", "inner")
        rt.dispatch_click(btn)
        assert "inner" in logs
        assert "outer" in logs


class TestDOMMutation:
    def test_create_and_append(self):
        dom = make_dom("""<html><body>
        <div id="container"></div>
        <script>
        var el = document.createElement("p");
        var t = document.createTextNode("new text");
        el.appendChild(t);
        document.getElementById("container").appendChild(el);
        console.log(document.getElementById("container").textContent);
        </script></body></html>""")
        logs = []
        rt = JSRuntime(dom, engine=ToyJSEngine(), on_log=lambda *a: logs.append(" ".join(a)))
        rt.run_scripts(dom)
        assert logs == ["new text"]

    def test_set_attribute(self):
        dom = make_dom("""<html><body>
        <div id="box"></div>
        <script>
        document.getElementById("box").setAttribute("class", "active");
        console.log(document.getElementById("box").getAttribute("class"));
        </script></body></html>""")
        logs = []
        rt = JSRuntime(dom, engine=ToyJSEngine(), on_log=lambda *a: logs.append(" ".join(a)))
        rt.run_scripts(dom)
        assert logs == ["active"]
