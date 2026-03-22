var __eventHandlers = {};

function __makeNode(handle) {
    if (handle === null || handle === undefined) return null;
    return {
        __handle: handle,
        get tagName() { return call_python("__getTagName", handle); },
        get textContent() { return call_python("__getTextContent", handle); },
        set textContent(v) { call_python("__setTextContent", handle, String(v)); },
        get innerHTML() { return call_python("__getInnerHTML", handle); },
        set innerHTML(v) { call_python("__setInnerHTML", handle, String(v)); },
        get parentNode() { return __makeNode(call_python("__getParent", handle)); },
        get children() {
            var hs = JSON.parse(call_python("__getChildren", handle) || "[]");
            var out = [];
            for (var i = 0; i < hs.length; i++) out.push(__makeNode(hs[i]));
            return out;
        },
        get id() { return call_python("__getAttr", handle, "id") || ""; },
        get className() { return call_python("__getAttr", handle, "class") || ""; },
        set className(v) { call_python("__setAttr", handle, "class", String(v)); },
        getAttribute: function(n) { return call_python("__getAttr", handle, n); },
        setAttribute: function(n, v) { call_python("__setAttr", handle, n, String(v)); },
        removeAttribute: function(n) { call_python("__setAttr", handle, n, ""); },
        appendChild: function(child) {
            call_python("__appendChild", handle, child.__handle);
            return child;
        },
        removeChild: function(child) {
            call_python("__removeChild", handle, child.__handle);
            return child;
        },
        querySelector: function(sel) {
            return __makeNode(call_python("__querySelector", sel, handle));
        },
        querySelectorAll: function(sel) {
            var hs = JSON.parse(call_python("__querySelectorAll", sel, handle) || "[]");
            var out = [];
            for (var i = 0; i < hs.length; i++) out.push(__makeNode(hs[i]));
            return out;
        },
        addEventListener: function(type, fn) {
            call_python("__registerEvent", handle, type);
            if (!__eventHandlers[handle]) __eventHandlers[handle] = {};
            if (!__eventHandlers[handle][type]) __eventHandlers[handle][type] = [];
            __eventHandlers[handle][type].push(fn);
        },
        style: {
            setProperty: function(p, v) { call_python("__setStyle", handle, p, v); },
            getPropertyValue: function(p) { return call_python("__getStyle", handle, p); }
        },
        classList: {
            add: function(n) { call_python("__classListOp", handle, "add", n); },
            remove: function(n) { call_python("__classListOp", handle, "remove", n); },
            toggle: function(n) { return call_python("__classListOp", handle, "toggle", n); },
            contains: function(n) { return call_python("__classListOp", handle, "contains", n); }
        }
    };
}

function __dispatchEvent(handle, type) {
    var handlers = (__eventHandlers[handle] || {})[type] || [];
    var evt = { type: type, target: __makeNode(handle), preventDefault: function(){}, stopPropagation: function(){} };
    for (var i = 0; i < handlers.length; i++) {
        handlers[i](evt);
    }
}

var document = {
    getElementById: function(id) { return __makeNode(call_python("__getElementById", id)); },
    querySelector: function(sel) { return __makeNode(call_python("__querySelector", sel)); },
    querySelectorAll: function(sel) {
        var hs = JSON.parse(call_python("__querySelectorAll", sel) || "[]");
        var out = [];
        for (var i = 0; i < hs.length; i++) out.push(__makeNode(hs[i]));
        return out;
    },
    createElement: function(tag) { return __makeNode(call_python("__createElement", tag)); },
    createTextNode: function(text) { return __makeNode(call_python("__createTextNode", text)); },
    get body() { return __makeNode(call_python("__getBody")); }
};

var console = {
    log: function() { var a = []; for (var i = 0; i < arguments.length; i++) a.push(String(arguments[i])); call_python("__log", a.join(" ")); },
    warn: function() { var a = []; for (var i = 0; i < arguments.length; i++) a.push(String(arguments[i])); call_python("__log", "[warn] " + a.join(" ")); },
    error: function() { var a = []; for (var i = 0; i < arguments.length; i++) a.push(String(arguments[i])); call_python("__log", "[error] " + a.join(" ")); }
};

var window = {
    alert: function(msg) { call_python("__alert", String(msg || "")); },
    document: document,
    console: console
};

function alert(msg) { call_python("__alert", String(msg || "")); }

/* -- fetch (ES5-compatible, sync) --------------------------------------- */
function fetch(url, options) {
    var r = JSON.parse(call_python("__fetch", String(url), options ? JSON.stringify(options) : "{}"));
    return {
        then: function(fn) { return fn({ok: r.ok, status: r.status, statusText: r.statusText,
            text: function() { return {then: function(f) { return f(r.body); }}; },
            json: function() { return {then: function(f) { return f(JSON.parse(r.body)); }}; }
        }); }
    };
}

/* -- XMLHttpRequest ----------------------------------------------------- */
function XMLHttpRequest() {
    this.readyState = 0; this.status = 0; this.responseText = "";
    this.onload = null; this.onerror = null; this._method = "GET"; this._url = "";
}
XMLHttpRequest.prototype.open = function(m, u) { this._method = m; this._url = u; this.readyState = 1; };
XMLHttpRequest.prototype.setRequestHeader = function() {};
XMLHttpRequest.prototype.send = function(body) {
    var r = JSON.parse(call_python("__xhrSend", this._method, this._url, body || ""));
    this.status = r.status; this.responseText = r.responseText; this.readyState = 4;
    if (this.onload) this.onload();
};

/* -- localStorage / sessionStorage -------------------------------------- */
var localStorage = {
    getItem: function(k) { return call_python("__storageGet", String(k)); },
    setItem: function(k, v) { call_python("__storageSet", String(k), String(v)); },
    removeItem: function(k) { call_python("__storageRemove", String(k)); },
    clear: function() { call_python("__storageClear"); }
};
var __sd = {};
var sessionStorage = {
    getItem: function(k) { return __sd[k] !== undefined ? __sd[k] : null; },
    setItem: function(k, v) { __sd[k] = String(v); },
    removeItem: function(k) { delete __sd[k]; },
    clear: function() { __sd = {}; }
};

/* -- location ----------------------------------------------------------- */
var location = JSON.parse(call_python("__getLocationJSON"));
window.location = location;
document.location = location;

/* -- encoding / misc ---------------------------------------------------- */
function encodeURIComponent(s) { return call_python("__encodeURIComponent", String(s)); }
function decodeURIComponent(s) { return call_python("__decodeURIComponent", String(s)); }
function encodeURI(s) { return call_python("__encodeURI", String(s)); }
function decodeURI(s) { return call_python("__decodeURI", String(s)); }
function btoa(s) { return call_python("__btoa", String(s)); }
function atob(s) { return call_python("__atob", String(s)); }
var navigator = { userAgent: "Pybrowser/1.0", language: "en-US" };
