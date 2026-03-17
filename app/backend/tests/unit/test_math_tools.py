"""Math tool — AST-based safe evaluation."""

from tools.math_tools import calculate


class TestCalculateBasicArithmetic:
    def test_addition(self):
        assert calculate("2 + 3") == "5"

    def test_multiplication(self):
        assert calculate("2 * 3 + 4") == "10"

    def test_division(self):
        assert float(calculate("10 / 3")) == pytest.approx(10 / 3)

    def test_power(self):
        assert calculate("2 ** 10") == "1024"

    def test_floor_division(self):
        assert calculate("7 // 2") == "3"

    def test_modulo(self):
        assert calculate("10 % 3") == "1"

    def test_negative(self):
        assert calculate("-5") == "-5"


class TestCalculateFunctions:
    def test_sqrt(self):
        assert calculate("sqrt(144)") == "12.0"

    def test_abs(self):
        assert calculate("abs(-5)") == "5"

    def test_round(self):
        assert calculate("round(3.14159)") == "3"


class TestCalculateConstants:
    def test_pi(self):
        import math
        assert calculate("pi") == str(math.pi)

    def test_e(self):
        import math
        assert calculate("e") == str(math.e)


class TestCalculateSecurityBlocking:
    """Verify that dangerous expressions are blocked."""

    def test_blocks_import(self):
        result = calculate("import os")
        assert "Error" in result

    def test_blocks_dunder_import(self):
        result = calculate('__import__("os")')
        assert "Error" in result

    def test_blocks_class_escape(self):
        result = calculate("().__class__.__bases__")
        assert "Error" in result

    def test_blocks_string_constant(self):
        result = calculate('"hello"')
        assert "Error" in result

    def test_blocks_unknown_function(self):
        result = calculate("exec('print(1)')")
        assert "Error" in result

    def test_blocks_unknown_variable(self):
        result = calculate("os")
        assert "Error" in result


import pytest
