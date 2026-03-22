var __eventHandlers = {};

function __makeNode(handle) {
    if (handle === null || handle === undefined) return null;
    return {
        __handle: handle,
        get tagName() { return __getTagName(handle); },
        get textContent() { return __getTextContent(handle); },
        set textContent(v) { __setTextContent(handle, String(v)); },
        get innerHTML() { return __getInnerHTML(handle); },
        set innerHTML(v) { __setInnerHTML(handle, String(v)); },
        get parentNode() { return __makeNode(__getParent(handle)); },
        get children() { return JSON.parse(__getChildren(handle) || "[]").map(__makeNode); },
        get id() { return __getAttr(handle, "id") || ""; },
        get className() { return __getAttr(handle, "class") || ""; },
        set className(v) { __setAttr(handle, "class", String(v)); },
        getAttribute(n) { return __getAttr(handle, n); },
        setAttribute(n, v) { __setAttr(handle, n, String(v)); },
        removeAttribute(n) { __setAttr(handle, n, ""); },
        appendChild(child) { __appendChild(handle, child.__handle); return child; },
        removeChild(child) { __removeChild(handle, child.__handle); return child; },
        querySelector(sel) { return __makeNode(__querySelector(sel, handle)); },
        querySelectorAll(sel) { return JSON.parse(__querySelectorAll(sel, handle) || "[]").map(__makeNode); },
        addEventListener(type, fn) {
            __registerEvent(handle, type);
            if (!__eventHandlers[handle]) __eventHandlers[handle] = {};
            if (!__eventHandlers[handle][type]) __eventHandlers[handle][type] = [];
            __eventHandlers[handle][type].push(fn);
        },
        style: {
            setProperty(p, v) { __setStyle(handle, p, v); },
            getPropertyValue(p) { return __getStyle(handle, p); }
        },
        classList: {
            add(n) { __classListOp(handle, "add", n); },
            remove(n) { __classListOp(handle, "remove", n); },
            toggle(n) { return __classListOp(handle, "toggle", n); },
            contains(n) { return __classListOp(handle, "contains", n); }
        },
        getContext(type) {
            if (type === "2d") {
                var w = parseInt(__getAttr(handle, "width")) || 300;
                var h = parseInt(__getAttr(handle, "height")) || 150;
                if (!__canvasContexts[handle]) {
                    var cid = __canvasCreate(w, h);
                    __setAttr(handle, "_canvas_id", String(cid));
                    __canvasContexts[handle] = new CanvasRenderingContext2D(cid, w, h);
                }
                return __canvasContexts[handle];
            }
            return null;
        },
        insertBefore(newNode, refNode) {
            __insertBefore(handle, newNode.__handle, refNode ? refNode.__handle : null);
            return newNode;
        },
        replaceChild(newNode, oldNode) {
            __replaceChild(handle, newNode.__handle, oldNode.__handle);
            return oldNode;
        },
        cloneNode(deep) {
            return __makeNode(__cloneNode(handle, !!deep));
        },
        closest(sel) {
            return __makeNode(__closest(handle, sel));
        },
        get dataset() {
            return new Proxy({}, {
                get(_, key) { return __getDataset(handle, key); },
                set(_, key, val) { __setDataset(handle, key, String(val)); return true; }
            });
        },
        get nodeType() { return __getTagName(handle) ? 1 : 3; },
        get firstChild() {
            var ch = JSON.parse(__getChildren(handle) || "[]");
            return ch.length > 0 ? __makeNode(ch[0]) : null;
        },
        get lastChild() {
            var ch = JSON.parse(__getChildren(handle) || "[]");
            return ch.length > 0 ? __makeNode(ch[ch.length - 1]) : null;
        },
        get nextSibling() { return null; },
        contains(other) {
            if (!other) return false;
            var n = other;
            while (n) {
                if (n.__handle === handle) return true;
                n = n.parentNode;
            }
            return false;
        }
    };
}

function __dispatchEvent(handle, type) {
    const handlers = (__eventHandlers[handle] || {})[type] || [];
    const evt = { type, target: __makeNode(handle), preventDefault() {}, stopPropagation() {} };
    for (const fn of handlers) fn(evt);
}

var document = {
    getElementById(id) { return __makeNode(__getElementById(id)); },
    querySelector(sel) { return __makeNode(__querySelector(sel)); },
    querySelectorAll(sel) { return JSON.parse(__querySelectorAll(sel) || "[]").map(__makeNode); },
    createElement(tag) { return __makeNode(__createElement(tag)); },
    createTextNode(text) { return __makeNode(__createTextNode(text)); },
    get body() { return __makeNode(__getBody()); }
};

var console = {
    log(...args) { __log(args.map(String).join(" ")); },
    warn(...args) { __log("[warn] " + args.map(String).join(" ")); },
    error(...args) { __log("[error] " + args.map(String).join(" ")); }
};

var history = {
    pushState(state, title, url) { __pushState(JSON.stringify(state || null), String(title), String(url)); },
    replaceState(state, title, url) { __replaceState(JSON.stringify(state || null), String(title), String(url)); },
    back() {},
    forward() {},
    length: 1
};

var window = {
    alert(msg) { __alert(String(msg || "")); },
    document, console, history, location,
    getComputedStyle(el) {
        return new Proxy({}, {
            get(_, prop) {
                var cssProp = prop.replace(/[A-Z]/g, m => "-" + m.toLowerCase());
                return __getComputedStyle(el.__handle, cssProp);
            }
        });
    },
    addEventListener(type, fn) {
        if (type === "DOMContentLoaded" || type === "load") fn();
    },
    dispatchEvent() {},
    innerWidth: 1200, innerHeight: 900,
};
function alert(msg) { __alert(String(msg || "")); }
document.addEventListener = function(type, fn) {
    if (type === "DOMContentLoaded" || type === "readystatechange") fn();
};
document.readyState = "complete";

/* -- fetch API (sync thenable) ------------------------------------------ */
function __syncThen(val) { return { then(fn) { return __syncThen(fn(val)); }, catch() { return this; } }; }
function fetch(url, options) {
    var result = JSON.parse(__fetch(String(url), options ? JSON.stringify(options) : "{}"));
    var response = {
        ok: result.ok, status: result.status, statusText: result.statusText,
        headers: { get(n) { return (result.headers || {})[n.toLowerCase()] || null; } },
        text() { return __syncThen(result.body); },
        json() { return __syncThen(JSON.parse(result.body)); },
    };
    return __syncThen(response);
}

/* -- XMLHttpRequest ----------------------------------------------------- */
function XMLHttpRequest() {
    this.readyState = 0; this.status = 0; this.responseText = "";
    this.onload = null; this.onerror = null; this.onreadystatechange = null;
    this._method = "GET"; this._url = ""; this._headers = {};
}
XMLHttpRequest.prototype.open = function(method, url) {
    this._method = method; this._url = url; this.readyState = 1;
};
XMLHttpRequest.prototype.setRequestHeader = function(k, v) { this._headers[k] = v; };
XMLHttpRequest.prototype.send = function(body) {
    var r = JSON.parse(__xhrSend(this._method, this._url, body || ""));
    this.status = r.status; this.responseText = r.responseText; this.readyState = 4;
    if (this.onreadystatechange) this.onreadystatechange();
    if (this.onload) this.onload();
};

/* -- localStorage ------------------------------------------------------- */
var localStorage = {
    getItem(k) { return __storageGet(String(k)); },
    setItem(k, v) { __storageSet(String(k), String(v)); },
    removeItem(k) { __storageRemove(String(k)); },
    clear() { __storageClear(); },
    get length() { return __storageLength(); },
    key(i) { return __storageKey(i); },
};

/* -- sessionStorage (in-memory only) ------------------------------------ */
var __sessionData = {};
var sessionStorage = {
    getItem(k) { return __sessionData[k] !== undefined ? __sessionData[k] : null; },
    setItem(k, v) { __sessionData[k] = String(v); },
    removeItem(k) { delete __sessionData[k]; },
    clear() { __sessionData = {}; },
    get length() { return Object.keys(__sessionData).length; },
    key(i) { var keys = Object.keys(__sessionData); return i < keys.length ? keys[i] : null; },
};

/* -- location ----------------------------------------------------------- */
var location = JSON.parse(__getLocationJSON());
window.location = location;
document.location = location;

/* -- encoding utilities ------------------------------------------------- */
function encodeURIComponent(s) { return __encodeURIComponent(String(s)); }
function decodeURIComponent(s) { return __decodeURIComponent(String(s)); }
function encodeURI(s) { return __encodeURI(String(s)); }
function decodeURI(s) { return __decodeURI(String(s)); }
function btoa(s) { return __btoa(String(s)); }
function atob(s) { return __atob(String(s)); }

/* -- misc stubs --------------------------------------------------------- */
function requestAnimationFrame(fn) { fn(Date.now()); return 0; }
function cancelAnimationFrame() {}
var navigator = { userAgent: "Pybrowser/1.0", language: "en-US", languages: ["en-US"], platform: "Python" };
var performance = { now() { return Date.now(); } };

/* -- WebSocket ---------------------------------------------------------- */
function WebSocket(url) {
    this.url = url;
    this.readyState = 0;
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    this._id = __wsConnect(url);
    if (this._id >= 0) {
        this.readyState = 1;
        if (this.onopen) this.onopen({ type: "open" });
    } else {
        this.readyState = 3;
        if (this.onerror) this.onerror({ type: "error" });
    }
}
WebSocket.prototype.send = function(data) {
    if (this.readyState === 1) __wsSend(this._id, String(data));
};
WebSocket.prototype.close = function() {
    __wsClose(this._id);
    this.readyState = 3;
    if (this.onclose) this.onclose({ type: "close" });
};
WebSocket.CONNECTING = 0; WebSocket.OPEN = 1; WebSocket.CLOSING = 2; WebSocket.CLOSED = 3;

/* -- Canvas 2D Context -------------------------------------------------- */
var __canvasContexts = {};
function CanvasRenderingContext2D(canvasId, w, h) {
    this._id = canvasId;
    this.fillStyle = "#000000";
    this.strokeStyle = "#000000";
    this.lineWidth = 1;
    this.font = "16px Helvetica";
    this.canvas = { width: w, height: h };
}
CanvasRenderingContext2D.prototype.fillRect = function(x, y, w, h) {
    __canvasFillRect(this._id, x, y, w, h, this.fillStyle);
};
CanvasRenderingContext2D.prototype.strokeRect = function(x, y, w, h) {
    __canvasStrokeRect(this._id, x, y, w, h, this.strokeStyle, this.lineWidth);
};
CanvasRenderingContext2D.prototype.clearRect = function(x, y, w, h) {
    __canvasClearRect(this._id, x, y, w, h);
};
CanvasRenderingContext2D.prototype.fillText = function(text, x, y) {
    var size = parseInt(this.font) || 16;
    __canvasFillText(this._id, String(text), x, y, this.fillStyle, size);
};
CanvasRenderingContext2D.prototype.beginPath = function() { this._path = []; };
CanvasRenderingContext2D.prototype.moveTo = function(x, y) { this._lastX = x; this._lastY = y; };
CanvasRenderingContext2D.prototype.lineTo = function(x, y) {
    __canvasLine(this._id, this._lastX || 0, this._lastY || 0, x, y, this.strokeStyle, this.lineWidth);
    this._lastX = x; this._lastY = y;
};
CanvasRenderingContext2D.prototype.stroke = function() {};
CanvasRenderingContext2D.prototype.fill = function() {};
CanvasRenderingContext2D.prototype.closePath = function() {};
