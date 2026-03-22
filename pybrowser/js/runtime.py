"""DOM bridge between the JS engine and the browser's DOM tree.

Supports two modes:
  - ToyJSEngine: Python objects shared directly (fast, full integration)
  - Native engines (QuickJS/Dukpy): call_python() bridge with JS-side shim
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote, unquote

from ..html_parser import Element, Node, Text
from .engine import DukpyEngine, JSEngine, QuickJSEngine, create_engine

STORAGE_DIR = os.path.expanduser("~/.pybrowser/storage")

_toy_imports_done = False


def _import_toy():
    global _toy_imports_done
    if not _toy_imports_done:
        global NativeFunction, JSFunction, JSObject, JS_UNDEFINED, _to_js_string
        from .interpreter import JS_UNDEFINED, JSFunction, JSObject, NativeFunction, _to_js_string
        _toy_imports_done = True


class JSRuntime:
    def __init__(self, dom: Element, engine: Optional[JSEngine] = None,
                 on_mutate: Optional[Callable] = None,
                 on_log: Optional[Callable] = None,
                 on_alert: Optional[Callable] = None,
                 base_url: Any = None) -> None:
        self.dom = dom
        self.engine = engine or create_engine()
        self._on_mutate = on_mutate
        self._on_log = on_log or (lambda *a: print("[console]", *a))
        self._on_alert = on_alert or (lambda msg: print("[alert]", msg))
        self._handles: Dict[int, Node] = {}
        self._node_to_handle: Dict[int, int] = {}
        self._next_handle = 1
        self._event_listeners: Dict[int, Dict[str, List[Any]]] = {}
        self._timers: List[tuple] = []
        self._is_native = isinstance(self.engine, (DukpyEngine, QuickJSEngine))
        self._base_url = base_url
        self._storage: Optional[Dict[str, str]] = None
        self._storage_domain = base_url.hostname if base_url else "local"

        if self._is_native:
            self._setup_native()
        else:
            _import_toy()
            self._setup_toy()

    # -- handle registry ----------------------------------------------------

    def _get_handle(self, node: Node) -> int:
        nid = id(node)
        if nid in self._node_to_handle:
            return self._node_to_handle[nid]
        h = self._next_handle
        self._next_handle += 1
        self._handles[h] = node
        self._node_to_handle[nid] = h
        return h

    def _get_node(self, handle: Any) -> Optional[Node]:
        if handle is None:
            return None
        return self._handles.get(int(handle))

    # ======================================================================
    # DUKPY ENGINE PATH -- call_python() bridge
    # ======================================================================

    def _setup_native(self) -> None:
        e = self.engine
        e.set_native_fn("__log", self._py_log)
        e.set_native_fn("__alert", self._py_alert)
        e.set_native_fn("__getElementById", self._py_get_element_by_id)
        e.set_native_fn("__querySelector", self._py_query_selector)
        e.set_native_fn("__querySelectorAll", self._py_query_selector_all)
        e.set_native_fn("__createElement", self._py_create_element)
        e.set_native_fn("__createTextNode", self._py_create_text_node)
        e.set_native_fn("__getAttr", self._py_get_attr)
        e.set_native_fn("__setAttr", self._py_set_attr)
        e.set_native_fn("__getTextContent", self._py_get_text_content)
        e.set_native_fn("__setTextContent", self._py_set_text_content)
        e.set_native_fn("__getInnerHTML", self._py_get_inner_html)
        e.set_native_fn("__setInnerHTML", self._py_set_inner_html)
        e.set_native_fn("__getTagName", self._py_get_tag_name)
        e.set_native_fn("__getParent", self._py_get_parent)
        e.set_native_fn("__getChildren", self._py_get_children)
        e.set_native_fn("__appendChild", self._py_append_child)
        e.set_native_fn("__removeChild", self._py_remove_child)
        e.set_native_fn("__getStyle", self._py_get_style)
        e.set_native_fn("__setStyle", self._py_set_style)
        e.set_native_fn("__classListOp", self._py_classlist_op)
        e.set_native_fn("__getBody", self._py_get_body)
        e.set_native_fn("__registerEvent", self._py_register_event)

        e.set_native_fn("__fetch", self._py_fetch)
        e.set_native_fn("__xhrSend", self._py_xhr_send)
        e.set_native_fn("__storageGet", self._py_storage_get)
        e.set_native_fn("__storageSet", self._py_storage_set)
        e.set_native_fn("__storageRemove", self._py_storage_remove)
        e.set_native_fn("__storageClear", self._py_storage_clear)
        e.set_native_fn("__storageLength", self._py_storage_length)
        e.set_native_fn("__storageKey", self._py_storage_key)
        e.set_native_fn("__getLocationJSON", self._py_get_location_json)
        e.set_native_fn("__insertBefore", self._py_insert_before)
        e.set_native_fn("__replaceChild", self._py_replace_child)
        e.set_native_fn("__cloneNode", self._py_clone_node)
        e.set_native_fn("__closest", self._py_closest)
        e.set_native_fn("__getDataset", self._py_get_dataset)
        e.set_native_fn("__setDataset", self._py_set_dataset)
        e.set_native_fn("__getComputedStyle", self._py_get_computed_style)
        e.set_native_fn("__pushState", self._py_push_state)
        e.set_native_fn("__replaceState", self._py_replace_state)
        e.set_native_fn("__wsConnect", self._py_ws_connect)
        e.set_native_fn("__wsSend", self._py_ws_send)
        e.set_native_fn("__wsClose", self._py_ws_close)

        from ..canvas2d import (
            canvas_clear,
            canvas_clear_rect,
            canvas_fill_rect,
            canvas_fill_text,
            canvas_line,
            canvas_stroke_rect,
            create_canvas,
        )
        e.set_native_fn("__canvasCreate", lambda w, h: create_canvas(int(w), int(h)))
        e.set_native_fn("__canvasFillRect", lambda cid, x, y, w, h, c: canvas_fill_rect(int(cid), x, y, w, h, str(c)))
        e.set_native_fn("__canvasStrokeRect", lambda cid, x, y, w, h, c, lw: canvas_stroke_rect(int(cid), x, y, w, h, str(c), lw))
        e.set_native_fn("__canvasFillText", lambda cid, t, x, y, c, s: canvas_fill_text(int(cid), str(t), x, y, str(c), s))
        e.set_native_fn("__canvasLine", lambda cid, x1, y1, x2, y2, c, lw: canvas_line(int(cid), x1, y1, x2, y2, str(c), lw))
        e.set_native_fn("__canvasClearRect", lambda cid, x, y, w, h: canvas_clear_rect(int(cid), x, y, w, h))
        e.set_native_fn("__canvasClear", lambda cid: canvas_clear(int(cid)))
        e.set_native_fn("__encodeURI", lambda s: quote(str(s), safe="~:/?#[]@!$&'()*+,;=-._"))
        e.set_native_fn("__encodeURIComponent", lambda s: quote(str(s), safe="~-._!*'()"))
        e.set_native_fn("__decodeURI", lambda s: unquote(str(s)))
        e.set_native_fn("__decodeURIComponent", lambda s: unquote(str(s)))
        e.set_native_fn("__btoa", lambda s: base64.b64encode(str(s).encode()).decode())
        e.set_native_fn("__atob", lambda s: base64.b64decode(str(s)).decode())

        is_dukpy = isinstance(self.engine, DukpyEngine)
        shim = _get_dukpy_shim() if is_dukpy else _get_quickjs_shim()
        self.engine.execute(shim)

    def _py_log(self, *args):
        self._on_log(*[str(a) for a in args])

    def _py_alert(self, msg=""):
        self._on_alert(str(msg))

    def _py_get_element_by_id(self, id_val):
        node = self._find_by_id(self.dom, str(id_val))
        return self._get_handle(node) if node else None

    def _py_query_selector(self, selector, root_handle=None):
        root = self._get_node(root_handle) if root_handle else self.dom
        results = self._query_all(str(selector), root or self.dom)
        return self._get_handle(results[0]) if results else None

    def _py_query_selector_all(self, selector, root_handle=None):
        root = self._get_node(root_handle) if root_handle else self.dom
        results = self._query_all(str(selector), root or self.dom)
        return json.dumps([self._get_handle(n) for n in results])

    def _py_create_element(self, tag):
        el = Element(str(tag).lower(), {}, None)
        el.style = {}
        el.children = []
        return self._get_handle(el)

    def _py_create_text_node(self, text):
        t = Text(str(text), None)
        t.style = {}
        return self._get_handle(t)

    def _py_get_attr(self, handle, name):
        node = self._get_node(handle)
        if isinstance(node, Element):
            return node.attributes.get(str(name))
        return None

    def _py_set_attr(self, handle, name, value):
        node = self._get_node(handle)
        if isinstance(node, Element):
            node.attributes[str(name)] = str(value)
            self._signal_mutation()

    def _py_get_text_content(self, handle):
        node = self._get_node(handle)
        return self._get_text_content_str(node) if node else ""

    def _py_set_text_content(self, handle, text):
        node = self._get_node(handle)
        if isinstance(node, Element):
            t = Text(str(text), node)
            t.style = {}
            node.children = [t]
            self._signal_mutation()

    def _py_get_inner_html(self, handle):
        node = self._get_node(handle)
        return self._get_inner_html_str(node) if isinstance(node, Element) else ""

    def _py_set_inner_html(self, handle, html):
        node = self._get_node(handle)
        if isinstance(node, Element):
            from ..html_parser import HTMLParser
            fragment = HTMLParser(str(html)).parse()
            body = None
            for c in fragment.children:
                if isinstance(c, Element) and c.tag == "body":
                    body = c
                    break
            children = body.children if body else fragment.children
            for c in children:
                c.parent = node
            node.children = list(children)
            self._signal_mutation()

    def _py_get_tag_name(self, handle):
        node = self._get_node(handle)
        return node.tag.upper() if isinstance(node, Element) else ""

    def _py_get_parent(self, handle):
        node = self._get_node(handle)
        if node and node.parent:
            return self._get_handle(node.parent)
        return None

    def _py_get_children(self, handle):
        node = self._get_node(handle)
        if isinstance(node, Element):
            return json.dumps([self._get_handle(c) for c in node.children if isinstance(c, Element)])
        return "[]"

    def _py_append_child(self, parent_handle, child_handle):
        parent = self._get_node(parent_handle)
        child = self._get_node(child_handle)
        if isinstance(parent, Element) and child:
            child.parent = parent
            parent.children.append(child)
            self._signal_mutation()
        return child_handle

    def _py_remove_child(self, parent_handle, child_handle):
        parent = self._get_node(parent_handle)
        child = self._get_node(child_handle)
        if isinstance(parent, Element) and child and child in parent.children:
            parent.children.remove(child)
            child.parent = None
            self._signal_mutation()
        return child_handle

    def _py_insert_before(self, parent_handle, new_handle, ref_handle):
        parent = self._get_node(parent_handle)
        new_node = self._get_node(new_handle)
        ref_node = self._get_node(ref_handle) if ref_handle else None
        if isinstance(parent, Element) and new_node:
            new_node.parent = parent
            if ref_node and ref_node in parent.children:
                idx = parent.children.index(ref_node)
                parent.children.insert(idx, new_node)
            else:
                parent.children.append(new_node)
            self._signal_mutation()
        return new_handle

    def _py_replace_child(self, parent_handle, new_handle, old_handle):
        parent = self._get_node(parent_handle)
        new_node = self._get_node(new_handle)
        old_node = self._get_node(old_handle)
        if isinstance(parent, Element) and new_node and old_node and old_node in parent.children:
            idx = parent.children.index(old_node)
            parent.children[idx] = new_node
            new_node.parent = parent
            old_node.parent = None
            self._signal_mutation()
        return old_handle

    def _py_clone_node(self, handle, deep=False):
        node = self._get_node(handle)
        if not node:
            return None
        clone = self._deep_clone(node) if deep else self._shallow_clone(node)
        return self._get_handle(clone)

    def _shallow_clone(self, node):
        if isinstance(node, Element):
            el = Element(node.tag, dict(node.attributes), None)
            el.style = dict(getattr(node, "style", {}))
            el.children = []
            return el
        elif isinstance(node, Text):
            t = Text(node.text, None)
            t.style = {}
            return t
        return None

    def _deep_clone(self, node):
        clone = self._shallow_clone(node)
        if isinstance(node, Element) and clone:
            for child in node.children:
                child_clone = self._deep_clone(child)
                if child_clone:
                    child_clone.parent = clone
                    clone.children.append(child_clone)
        return clone

    def _py_closest(self, handle, selector):
        node = self._get_node(handle)
        selector = str(selector).strip()
        while node:
            if isinstance(node, Element):
                if selector.startswith("#") and node.attributes.get("id") == selector[1:]:
                    return self._get_handle(node)
                elif selector.startswith(".") and selector[1:] in node.attributes.get("class", "").split():
                    return self._get_handle(node)
                elif node.tag == selector.lower():
                    return self._get_handle(node)
            node = getattr(node, "parent", None)
        return None

    def _py_get_dataset(self, handle, key):
        node = self._get_node(handle)
        if isinstance(node, Element):
            return node.attributes.get(f"data-{key}", None)
        return None

    def _py_set_dataset(self, handle, key, value):
        node = self._get_node(handle)
        if isinstance(node, Element):
            node.attributes[f"data-{key}"] = str(value)
            self._signal_mutation()

    def _py_push_state(self, state, title, url):
        if self._base_url and url:
            resolved = self._base_url.resolve(str(url))
            from ..url import Url
            self._base_url = Url(resolved)

    def _py_replace_state(self, state, title, url):
        self._py_push_state(state, title, url)

    def _py_get_computed_style(self, handle, prop):
        node = self._get_node(handle)
        if isinstance(node, Element) and hasattr(node, "style"):
            return node.style.get(str(prop), "")
        return ""

    def _py_get_style(self, handle, prop):
        node = self._get_node(handle)
        if isinstance(node, Element) and hasattr(node, "style"):
            return node.style.get(str(prop), "")
        return ""

    def _py_set_style(self, handle, prop, value):
        node = self._get_node(handle)
        if isinstance(node, Element):
            if not hasattr(node, "_js_style"):
                node._js_style = {}
            node._js_style[str(prop)] = str(value)
            self._signal_mutation()

    def _py_classlist_op(self, handle, op, name):
        node = self._get_node(handle)
        if not isinstance(node, Element):
            return False
        classes = node.attributes.get("class", "").split()
        if op == "add":
            if name not in classes:
                classes.append(name)
        elif op == "remove":
            classes = [c for c in classes if c != name]
        elif op == "toggle":
            if name in classes:
                classes = [c for c in classes if c != name]
            else:
                classes.append(name)
        elif op == "contains":
            return name in classes
        node.attributes["class"] = " ".join(classes)
        self._signal_mutation()
        return name in node.attributes.get("class", "").split()

    def _py_get_body(self):
        body = self._find_body()
        return self._get_handle(body) if body else None

    def _py_register_event(self, handle, event_type):
        h = int(handle)
        if h not in self._event_listeners:
            self._event_listeners[h] = {}
        if event_type not in self._event_listeners[h]:
            self._event_listeners[h][event_type] = []
        self._event_listeners[h][event_type].append("__dukpy_js_side")

    # ======================================================================
    # WEB APIs -- fetch, XHR, localStorage, location
    # ======================================================================

    def _check_cors(self, resolved_url: str, resp_headers: dict) -> bool:
        if not self._base_url:
            return True
        from ..url import Url
        target = Url(resolved_url)
        if target.origin == self._base_url.origin:
            return True
        acao = resp_headers.get("access-control-allow-origin", "")
        return acao == "*" or acao == self._base_url.origin

    def _py_fetch(self, url, options_json="{}"):
        from ..url import Url
        try:
            opts = json.loads(str(options_json)) if options_json and options_json != "{}" else {}
        except (json.JSONDecodeError, TypeError):
            opts = {}
        method = opts.get("method", "GET").upper()
        resolved = self._base_url.resolve(str(url)) if self._base_url else str(url)
        try:
            url_obj = Url(resolved)
            status, headers, body = url_obj.request()
            if not self._check_cors(resolved, headers):
                return json.dumps({"status": 0, "ok": False,
                                   "statusText": "CORS error: blocked by policy",
                                   "headers": {}, "body": ""})
            return json.dumps({
                "status": status, "ok": 200 <= status < 300,
                "statusText": "OK" if 200 <= status < 300 else "Error",
                "headers": headers, "body": body,
            })
        except Exception as e:
            return json.dumps({"status": 0, "ok": False, "statusText": str(e),
                               "headers": {}, "body": ""})

    def _py_xhr_send(self, method, url, body=""):
        from ..url import Url
        resolved = self._base_url.resolve(str(url)) if self._base_url else str(url)
        try:
            url_obj = Url(resolved)
            status, headers, resp_body = url_obj.request()
            if not self._check_cors(resolved, headers):
                return json.dumps({"status": 0, "responseText": "",
                                   "headers": {}, "readyState": 4})
            return json.dumps({"status": status, "responseText": resp_body,
                               "headers": headers, "readyState": 4})
        except Exception as e:
            return json.dumps({"status": 0, "responseText": "",
                               "headers": {}, "readyState": 4})

    def _load_storage(self) -> Dict[str, str]:
        if self._storage is not None:
            return self._storage
        path = os.path.join(STORAGE_DIR, self._storage_domain + ".json")
        try:
            with open(path) as f:
                self._storage = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._storage = {}
        return self._storage

    def _save_storage(self) -> None:
        os.makedirs(STORAGE_DIR, exist_ok=True)
        path = os.path.join(STORAGE_DIR, self._storage_domain + ".json")
        with open(path, "w") as f:
            json.dump(self._storage or {}, f)

    def _py_storage_get(self, key):
        return self._load_storage().get(str(key))

    def _py_storage_set(self, key, value):
        self._load_storage()[str(key)] = str(value)
        self._save_storage()

    def _py_storage_remove(self, key):
        self._load_storage().pop(str(key), None)
        self._save_storage()

    def _py_storage_clear(self):
        self._storage = {}
        self._save_storage()

    def _py_storage_length(self):
        return len(self._load_storage())

    def _py_storage_key(self, index):
        keys = list(self._load_storage().keys())
        idx = int(index)
        return keys[idx] if 0 <= idx < len(keys) else None

    def _py_get_location_json(self):
        if not self._base_url:
            return json.dumps({"href": "", "protocol": "", "hostname": "",
                               "port": "", "pathname": "/", "search": "", "hash": ""})
        u = self._base_url
        path = u.path
        search = ""
        hash_val = ""
        if "?" in path:
            path, search = path.split("?", 1)
            search = "?" + search
        if "#" in path:
            path, hash_val = path.split("#", 1)
            hash_val = "#" + hash_val
        return json.dumps({
            "href": u.url, "protocol": u.protocol + ":",
            "hostname": u.hostname, "port": str(u.port),
            "pathname": path, "search": search, "hash": hash_val,
            "origin": u.origin,
        })

    # -- WebSocket ----------------------------------------------------------

    _ws_connections: dict = {}
    _ws_next_id: int = 1

    def _py_ws_connect(self, url):
        import base64 as _b64
        import socket as _socket
        try:
            url = str(url)
            proto = "wss" if url.startswith("wss://") else "ws"
            rest = url.split("://", 1)[1]
            host = rest.split("/")[0]
            path = "/" + rest.split("/", 1)[1] if "/" in rest else "/"
            port = 443 if proto == "wss" else 80
            if ":" in host:
                host, port = host.split(":")
                port = int(port)

            sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            if proto == "wss":
                import ssl as _ssl
                ctx = _ssl.create_default_context()
                sock = ctx.wrap_socket(sock, server_hostname=host)
            sock.connect((host, port))
            sock.setblocking(False)

            key = _b64.b64encode(os.urandom(16)).decode()
            req = f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
            req += "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            req += f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            sock.setblocking(True)
            sock.send(req.encode())
            resp = sock.recv(4096).decode()
            sock.setblocking(False)

            if "101" not in resp:
                sock.close()
                return -1

            ws_id = self._ws_next_id
            self.__class__._ws_next_id += 1
            self._ws_connections[ws_id] = sock
            return ws_id
        except Exception:
            return -1

    def _py_ws_send(self, ws_id, message):
        sock = self._ws_connections.get(int(ws_id))
        if not sock:
            return False
        try:
            data = str(message).encode("utf-8")
            frame = bytearray()
            frame.append(0x81)
            length = len(data)
            if length < 126:
                frame.append(0x80 | length)
            elif length < 65536:
                frame.append(0x80 | 126)
                frame.extend(length.to_bytes(2, "big"))
            mask = os.urandom(4)
            frame.extend(mask)
            for i, b in enumerate(data):
                frame.append(b ^ mask[i % 4])
            sock.setblocking(True)
            sock.send(bytes(frame))
            sock.setblocking(False)
            return True
        except Exception:
            return False

    def _py_ws_close(self, ws_id):
        sock = self._ws_connections.pop(int(ws_id), None)
        if sock:
            try:
                sock.close()
            except Exception:
                pass

    # ======================================================================
    # TOY JS ENGINE PATH -- direct Python object sharing
    # ======================================================================

    def _setup_toy(self) -> None:
        e = self.engine
        console = JSObject({
            "log": NativeFunction("log", lambda *a: self._on_log(*(_to_js_string(v) for v in a))),
            "warn": NativeFunction("warn", lambda *a: self._on_log("[warn]", *(_to_js_string(v) for v in a))),
            "error": NativeFunction("error", lambda *a: self._on_log("[error]", *(_to_js_string(v) for v in a))),
        })
        e.set_global("console", console)
        e.set_native_fn("alert", lambda msg="": self._on_alert(_to_js_string(msg)))
        e.set_global("document", self._make_document_toy())
        e.set_global("window", self._make_window_toy())
        e.set_global("localStorage", self._make_storage_toy(self._load_storage, self._save_storage))
        e.set_global("sessionStorage", self._make_storage_toy.__func__(self, lambda s=self: {}, lambda s=None: None) if False else self._make_session_toy())
        e.set_global("location", self._make_location_toy())
        e.set_native_fn("fetch", self._toy_fetch)
        e.set_native_fn("encodeURIComponent", lambda s: quote(str(s), safe="~-._!*'()"))
        e.set_native_fn("decodeURIComponent", lambda s: unquote(str(s)))
        e.set_native_fn("btoa", lambda s: base64.b64encode(str(s).encode()).decode())
        e.set_native_fn("atob", lambda s: base64.b64decode(str(s)).decode())
        e.set_global("navigator", JSObject({"userAgent": "Pybrowser/1.0", "language": "en-US"}))

    def _make_document_toy(self):
        doc = JSObject()
        doc["getElementById"] = NativeFunction("getElementById", self._toy_get_element_by_id)
        doc["querySelector"] = NativeFunction("querySelector", self._toy_query_selector)
        doc["querySelectorAll"] = NativeFunction("querySelectorAll", self._toy_query_selector_all)
        doc["createElement"] = NativeFunction("createElement", self._toy_create_element)
        doc["createTextNode"] = NativeFunction("createTextNode", self._toy_create_text_node)
        doc["body"] = self._wrap_node_toy(self._find_body())
        return doc

    def _make_window_toy(self):
        win = JSObject()
        win["innerWidth"] = 1200
        win["innerHeight"] = 900
        win["alert"] = NativeFunction("alert", lambda msg="": self._on_log("[alert]", str(msg)))
        win["setTimeout"] = NativeFunction("setTimeout", self._set_timeout)
        win["setInterval"] = NativeFunction("setInterval", self._set_interval)
        return win

    def _wrap_node_toy(self, node):
        if node is None:
            return None
        handle = self._get_handle(node)
        obj = JSObject()
        obj["__handle__"] = handle
        if isinstance(node, Element):
            obj["tagName"] = node.tag.upper()
            obj["id"] = node.attributes.get("id", "")
            obj["className"] = node.attributes.get("class", "")
            obj["children"] = NativeFunction("children", lambda: [self._wrap_node_toy(c) for c in node.children if isinstance(c, Element)])
            obj["childNodes"] = NativeFunction("childNodes", lambda: [self._wrap_node_toy(c) for c in node.children])
        elif isinstance(node, Text):
            obj["tagName"] = ""
            obj["nodeType"] = 3

        obj._getters["textContent"] = lambda: self._get_text_content_str(node)
        obj._getters["innerHTML"] = lambda: self._get_inner_html_str(node) if isinstance(node, Element) else ""

        def _set_text_content(val):
            if isinstance(node, Element):
                t = Text(str(val), node)
                t.style = {}
                node.children = [t]
                self._signal_mutation()
            elif isinstance(node, Text):
                node.text = str(val)
                self._signal_mutation()

        def _set_inner_html(val):
            if isinstance(node, Element):
                from ..html_parser import HTMLParser
                frag = HTMLParser(str(val)).parse()
                body = None
                for c in frag.children:
                    if isinstance(c, Element) and c.tag == "body":
                        body = c
                        break
                children = body.children if body else frag.children
                for c in children:
                    c.parent = node
                node.children = list(children)
                self._signal_mutation()

        obj._setters["textContent"] = _set_text_content
        obj._setters["innerHTML"] = _set_inner_html
        obj._setters["className"] = lambda v: (node.attributes.__setitem__("class", str(v)), self._signal_mutation()) if isinstance(node, Element) else None

        obj["parentNode"] = NativeFunction("parentNode", lambda: self._wrap_node_toy(node.parent))
        obj["getAttribute"] = NativeFunction("getAttribute",
            lambda name: node.attributes.get(name, None) if isinstance(node, Element) else None)
        obj["setAttribute"] = NativeFunction("setAttribute",
            lambda name, val: self._set_attribute(node, name, val))
        obj["addEventListener"] = NativeFunction("addEventListener",
            lambda etype, fn: self._add_event_listener(handle, etype, fn))
        obj["appendChild"] = NativeFunction("appendChild",
            lambda child_obj: self._toy_append_child(node, child_obj))
        obj["removeChild"] = NativeFunction("removeChild",
            lambda child_obj: self._toy_remove_child(node, child_obj))
        obj["querySelector"] = NativeFunction("querySelector",
            lambda sel: self._toy_query_selector(sel, node))
        obj["querySelectorAll"] = NativeFunction("querySelectorAll",
            lambda sel: self._toy_query_selector_all(sel, node))
        obj["style"] = self._make_style_proxy_toy(node)
        obj["classList"] = self._make_classlist_toy(node)
        return obj

    def _make_style_proxy_toy(self, node):
        s = JSObject()
        if not isinstance(node, Element):
            return s
        ns = getattr(node, "style", {})
        s["setProperty"] = NativeFunction("setProperty", lambda p, v: self._set_style_node(node, p, v))
        s["getPropertyValue"] = NativeFunction("getPropertyValue", lambda p: ns.get(p, ""))
        for prop in ("color", "backgroundColor", "fontSize", "fontWeight", "display",
                     "margin", "padding", "width", "height", "textAlign", "border", "opacity"):
            css_prop = _camel_to_css(prop)
            s[prop] = ns.get(css_prop, "")
        return s

    def _make_classlist_toy(self, node):
        cl = JSObject()
        if not isinstance(node, Element):
            return cl
        def gc(): return node.attributes.get("class", "").split()
        def sc(c): node.attributes["class"] = " ".join(c)
        cl["add"] = NativeFunction("add", lambda *n: sc(list(set(gc()) | set(n))))
        cl["remove"] = NativeFunction("remove", lambda *n: sc([c for c in gc() if c not in n]))
        cl["toggle"] = NativeFunction("toggle", lambda n: sc([c for c in gc() if c != n]) if n in gc() else sc(gc() + [n]))
        cl["contains"] = NativeFunction("contains", lambda n: n in gc())
        return cl

    def _toy_get_element_by_id(self, id_val):
        node = self._find_by_id(self.dom, str(id_val))
        return self._wrap_node_toy(node) if node else None

    def _toy_query_selector(self, selector, root=None):
        results = self._query_all(str(selector), root or self.dom)
        return self._wrap_node_toy(results[0]) if results else None

    def _toy_query_selector_all(self, selector, root=None):
        results = self._query_all(str(selector), root or self.dom)
        return [self._wrap_node_toy(n) for n in results]

    def _toy_create_element(self, tag):
        el = Element(str(tag).lower(), {}, None)
        el.style = {}
        el.children = []
        return self._wrap_node_toy(el)

    def _toy_create_text_node(self, text):
        t = Text(str(text), None)
        t.style = {}
        return self._wrap_node_toy(t)

    def _toy_append_child(self, parent, child_obj):
        if not isinstance(parent, Element) or not isinstance(child_obj, dict):
            return None
        child_node = self._get_node(child_obj.get("__handle__"))
        if child_node is None:
            return None
        child_node.parent = parent
        parent.children.append(child_node)
        self._signal_mutation()
        return child_obj

    def _toy_remove_child(self, parent, child_obj):
        if not isinstance(parent, Element) or not isinstance(child_obj, dict):
            return None
        child_node = self._get_node(child_obj.get("__handle__"))
        if child_node and child_node in parent.children:
            parent.children.remove(child_node)
            child_node.parent = None
            self._signal_mutation()
        return child_obj

    def _make_storage_toy(self, loader, saver):
        s = JSObject()
        s["getItem"] = NativeFunction("getItem", lambda k: loader().get(str(k)))
        s["setItem"] = NativeFunction("setItem", lambda k, v: (loader().__setitem__(str(k), str(v)), saver()))
        s["removeItem"] = NativeFunction("removeItem", lambda k: (loader().pop(str(k), None), saver()))
        s["clear"] = NativeFunction("clear", lambda: (loader().clear(), saver()))
        return s

    def _make_session_toy(self):
        data = {}
        s = JSObject()
        s["getItem"] = NativeFunction("getItem", lambda k: data.get(str(k)))
        s["setItem"] = NativeFunction("setItem", lambda k, v: data.__setitem__(str(k), str(v)))
        s["removeItem"] = NativeFunction("removeItem", lambda k: data.pop(str(k), None))
        s["clear"] = NativeFunction("clear", lambda: data.clear())
        return s

    def _make_location_toy(self):
        loc_data = json.loads(self._py_get_location_json())
        return JSObject(loc_data)

    def _toy_fetch(self, url, options=None):
        result_json = self._py_fetch(str(url), json.dumps(options) if isinstance(options, dict) else "{}")
        result = json.loads(result_json)
        resp = JSObject({
            "ok": result["ok"], "status": result["status"],
            "statusText": result["statusText"],
            "text": NativeFunction("text", lambda: result["body"]),
            "json": NativeFunction("json", lambda: json.loads(result["body"])),
        })
        return resp

    def _set_attribute(self, node, name, value):
        if isinstance(node, Element):
            node.attributes[str(name)] = str(value)
            self._signal_mutation()

    def _set_style_node(self, node, prop, value):
        if isinstance(node, Element):
            if not hasattr(node, "_js_style"):
                node._js_style = {}
            node._js_style[str(prop)] = str(value)
            self._signal_mutation()

    # ======================================================================
    # SHARED HELPERS
    # ======================================================================

    def _find_body(self):
        def find(node):
            if isinstance(node, Element) and node.tag == "body":
                return node
            if isinstance(node, Element):
                for c in node.children:
                    r = find(c)
                    if r: return r
            return None
        return find(self.dom)

    def _find_by_id(self, root, id_val):
        if isinstance(root, Element):
            if root.attributes.get("id") == id_val:
                return root
            for c in root.children:
                r = self._find_by_id(c, id_val)
                if r: return r
        return None

    def _query_all(self, selector, root):
        selector = selector.strip()
        results = []
        def match(node):
            for part in selector.split(","):
                part = part.strip()
                if part.startswith("#"):
                    if node.attributes.get("id") == part[1:]: return True
                elif part.startswith("."):
                    if part[1:] in node.attributes.get("class", "").split(): return True
                else:
                    if node.tag == part.lower(): return True
            return False
        def walk(node):
            if isinstance(node, Element):
                if match(node): results.append(node)
                for c in node.children: walk(c)
        walk(root)
        return results

    def _get_text_content_str(self, node):
        if isinstance(node, Text): return node.text
        if isinstance(node, Element):
            return "".join(self._get_text_content_str(c) for c in node.children)
        return ""

    def _get_inner_html_str(self, node):
        if not isinstance(node, Element): return ""
        parts = []
        for c in node.children:
            if isinstance(c, Text): parts.append(c.text)
            elif isinstance(c, Element):
                attrs = "".join(f' {k}="{v}"' for k, v in c.attributes.items())
                parts.append(f"<{c.tag}{attrs}>{self._get_inner_html_str(c)}</{c.tag}>")
        return "".join(parts)

    def _signal_mutation(self):
        if self._on_mutate:
            self._on_mutate()

    # -- event system -------------------------------------------------------

    def _add_event_listener(self, handle, event_type, callback):
        if handle not in self._event_listeners:
            self._event_listeners[handle] = {}
        if event_type not in self._event_listeners[handle]:
            self._event_listeners[handle][event_type] = []
        self._event_listeners[handle][event_type].append(callback)

    def dispatch_event(self, node, event_type, event_obj=None):
        handle = self._get_handle(node)
        listeners = self._event_listeners.get(handle, {}).get(event_type, [])
        if not listeners:
            return False

        if self._is_native:
            try:
                self.engine.execute(f"__dispatchEvent({handle}, {json.dumps(event_type)})")
            except Exception:
                pass
        else:
            _import_toy()
            evt = JSObject(event_obj or {})
            evt["type"] = event_type
            evt["target"] = self._wrap_node_toy(node)
            evt["preventDefault"] = NativeFunction("preventDefault", lambda: None)
            evt["stopPropagation"] = NativeFunction("stopPropagation", lambda: None)
            for callback in listeners:
                if isinstance(callback, (JSFunction, NativeFunction)):
                    try:
                        self.engine.interp._call(callback, [evt], self.engine.interp.global_env)
                    except Exception:
                        pass
        return True

    def dispatch_click(self, node):
        current = node
        handled = False
        while current:
            if self.dispatch_event(current, "click"):
                handled = True
            current = getattr(current, "parent", None)
        return handled

    # -- timers -------------------------------------------------------------

    def _set_timeout(self, fn, ms=0):
        tid = len(self._timers) + 1
        self._timers.append(("timeout", fn, ms, tid))
        return tid

    def _set_interval(self, fn, ms=0):
        tid = len(self._timers) + 1
        self._timers.append(("interval", fn, ms, tid))
        return tid

    def get_pending_timers(self):
        timers = list(self._timers)
        self._timers = [t for t in self._timers if t[0] == "interval"]
        return timers

    # -- script execution ---------------------------------------------------

    def run_scripts(self, dom, base_url=None):
        from ..url import Url
        for tag, code in self._collect_scripts(dom):
            src = tag.attributes.get("src", "") if isinstance(tag, Element) else ""
            if src and base_url:
                try:
                    code = Url(base_url.resolve(src)).fetch()
                except Exception:
                    continue
            if code:
                self.engine.execute(code)

    def _collect_scripts(self, node):
        scripts = []
        if isinstance(node, Element):
            if node.tag == "script":
                code = ""
                for c in node.children:
                    if isinstance(c, Text): code += c.text
                scripts.append((node, code))
            for c in node.children:
                scripts.extend(self._collect_scripts(c))
        return scripts


def _camel_to_css(name):
    import re
    return re.sub(r"([A-Z])", lambda m: "-" + m.group(1).lower(), name)


# ---------------------------------------------------------------------------
# JS shim loading
# ---------------------------------------------------------------------------

def _load_shim(name: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "shims", name)
    with open(path) as f:
        return f.read()

_QUICKJS_JS_SHIM: Optional[str] = None
_DUKPY_JS_SHIM: Optional[str] = None

def _get_quickjs_shim() -> str:
    global _QUICKJS_JS_SHIM
    if _QUICKJS_JS_SHIM is None:
        _QUICKJS_JS_SHIM = _load_shim("quickjs_shim.js")
    return _QUICKJS_JS_SHIM

def _get_dukpy_shim() -> str:
    global _DUKPY_JS_SHIM
    if _DUKPY_JS_SHIM is None:
        _DUKPY_JS_SHIM = _load_shim("dukpy_shim.js")
    return _DUKPY_JS_SHIM

