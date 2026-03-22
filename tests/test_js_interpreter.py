from pybrowser.js.interpreter import Interpreter, NativeFunction


def interp():
    return Interpreter()


class TestArithmetic:
    def test_add(self):
        assert interp().execute("1 + 2") == 3.0

    def test_subtract(self):
        assert interp().execute("10 - 3") == 7.0

    def test_multiply(self):
        assert interp().execute("4 * 5") == 20.0

    def test_divide(self):
        assert interp().execute("10 / 4") == 2.5

    def test_modulo(self):
        assert interp().execute("7 % 3") == 1.0


class TestVariables:
    def test_var_decl(self):
        i = interp()
        i.execute('var x = 42;')
        assert i.execute("x") == 42.0

    def test_string_concat(self):
        i = interp()
        i.execute('var a = "hello"; var b = " world";')
        assert i.execute("a + b") == "hello world"

    def test_number_to_string_concat(self):
        assert interp().execute('"val: " + 42') == "val: 42"


class TestFunctions:
    def test_basic_function(self):
        i = interp()
        i.execute("function add(a, b) { return a + b; }")
        assert i.execute("add(3, 4)") == 7.0

    def test_closure(self):
        i = interp()
        i.execute("""
        function counter() {
            var n = 0;
            return function() { n += 1; return n; };
        }
        var c = counter();
        """)
        assert i.execute("c()") == 1.0
        assert i.execute("c()") == 2.0
        assert i.execute("c()") == 3.0

    def test_recursion(self):
        i = interp()
        i.execute("""
        function fact(n) {
            if (n <= 1) return 1;
            return n * fact(n - 1);
        }
        """)
        assert i.execute("fact(5)") == 120.0


class TestControlFlow:
    def test_if_true(self):
        assert interp().execute("if (true) { 1; } else { 2; }") == 1.0

    def test_if_false(self):
        assert interp().execute("if (false) { 1; } else { 2; }") == 2.0

    def test_while_loop(self):
        i = interp()
        i.execute("var s = 0; var i = 0; while (i < 5) { s += i; i++; }")
        assert i.execute("s") == 10.0

    def test_for_loop(self):
        i = interp()
        i.execute("var s = 0; for (var j = 0; j < 4; j++) { s += j; }")
        assert i.execute("s") == 6.0

    def test_break(self):
        i = interp()
        i.execute("var x = 0; while (true) { x++; if (x >= 3) break; }")
        assert i.execute("x") == 3.0

    def test_ternary(self):
        assert interp().execute('true ? "yes" : "no"') == "yes"


class TestObjects:
    def test_object_literal(self):
        i = interp()
        i.execute("var o = { x: 1, y: 2 };")
        assert i.execute("o.x") == 1.0
        assert i.execute("o.y") == 2.0

    def test_object_mutation(self):
        i = interp()
        i.execute("var o = {}; o.name = 'test';")
        assert i.execute("o.name") == "test"


class TestArrays:
    def test_array_access(self):
        i = interp()
        i.execute("var a = [10, 20, 30];")
        assert i.execute("a[1]") == 20.0
        assert i.execute("a.length") == 3

    def test_array_push(self):
        i = interp()
        i.execute("var a = [1]; a.push(2); a.push(3);")
        assert i.execute("a.length") == 3

    def test_array_join(self):
        i = interp()
        i.execute('var a = ["a", "b", "c"];')
        assert i.execute('a.join("-")') == "a-b-c"


class TestStrings:
    def test_length(self):
        assert interp().execute('"hello".length') == 5

    def test_toUpperCase(self):
        assert interp().execute('"hello".toUpperCase()') == "HELLO"

    def test_trim(self):
        assert interp().execute('"  hi  ".trim()') == "hi"

    def test_split(self):
        i = interp()
        i.execute('var parts = "a,b,c".split(",");')
        assert i.execute("parts.length") == 3
        assert i.execute("parts[0]") == "a"

    def test_includes(self):
        assert interp().execute('"hello world".includes("world")') is True


class TestNativeFunctions:
    def test_native_callback(self):
        i = interp()
        captured = []
        i.global_env.define("capture", NativeFunction("capture", lambda v: captured.append(v)))
        i.execute('capture("hello");')
        assert captured == ["hello"]

    def test_typeof(self):
        assert interp().execute('typeof 42') == "number"
        assert interp().execute('typeof "hi"') == "string"
        assert interp().execute('typeof true') == "boolean"
        assert interp().execute('typeof null') == "object"
        assert interp().execute('typeof undefined') == "undefined"


class TestTryCatch:
    def test_catch(self):
        i = interp()
        i.execute("""
        var result = "none";
        try {
            throw "oops";
        } catch (e) {
            result = "caught";
        }
        """)
        assert i.execute("result") == "caught"
