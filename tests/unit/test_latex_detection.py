"""
Unit Tests for LaTeX Detection

Tests for the LaTeX detection heuristics used to determine whether a page
needs KaTeX loaded. The key challenge is distinguishing genuine LaTeX math
notation ($E = mc^2$) from currency amounts ($50), which also use dollar
signs.

Version: v0.9.1-beta
"""

import sys
import os

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import pytest
from telar.latex import has_latex, protect_latex, restore_latex


class TestDisplayMath:
    """$$...$$ display math — always detected."""

    def test_simple_display_math(self):
        assert has_latex("Some text $$E = mc^2$$ more text")

    def test_multiline_display_math(self):
        assert has_latex("Before\n$$\n\\sum_{i=1}^n x_i\n$$\nAfter")

    def test_display_math_with_align(self):
        assert has_latex("$$\\begin{align} a &= b \\\\ c &= d \\end{align}$$")


class TestInlineMathPositive:
    """$...$ inline math with LaTeX-like characters — detected."""

    def test_simple_equation(self):
        assert has_latex("The equation $E = mc^2$ is famous")

    def test_greek_letter(self):
        assert has_latex("The angle $\\alpha$ is acute")

    def test_subscript(self):
        assert has_latex("The variable $x_1$ is positive")

    def test_braces(self):
        assert has_latex("The fraction $\\frac{a}{b}$ simplifies")

    def test_superscript_only(self):
        assert has_latex("Calculate $x^2$")


class TestInlineMathFalsePositives:
    """$...$ that should NOT be detected as LaTeX."""

    def test_currency_amount(self):
        assert not has_latex("The price is $50")

    def test_currency_range(self):
        assert not has_latex("Between $20 and $30")

    def test_currency_with_comma(self):
        assert not has_latex("It costs $1,000")

    def test_dollar_with_space_after(self):
        assert not has_latex("$ amount is large")

    def test_single_dollar_sign(self):
        assert not has_latex("The $ sign is a symbol")

    def test_no_latex_chars(self):
        assert not has_latex("$abc$")


class TestBeginEnvironments:
    """\\begin{...} environments — always detected."""

    def test_align(self):
        assert has_latex("\\begin{align} x &= y \\end{align}")

    def test_cases(self):
        assert has_latex("\\begin{cases} x > 0 \\\\ x \\leq 0 \\end{cases}")

    def test_pmatrix(self):
        assert has_latex("\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}")


class TestAlternativeDelimiters:
    """\\(...\\) and \\[...\\] — always detected."""

    def test_inline_parens(self):
        assert has_latex("The value \\(x + y\\) is positive")

    def test_display_brackets(self):
        assert has_latex("\\[\\sum_{i=1}^n x_i = S\\]")


class TestNoLatex:
    """Plain text without any LaTeX."""

    def test_plain_text(self):
        assert not has_latex("This is a simple paragraph.")

    def test_empty_string(self):
        assert not has_latex("")

    def test_html_content(self):
        assert not has_latex("<p>Some <strong>HTML</strong> content</p>")

    def test_markdown(self):
        assert not has_latex("# Heading\n\nSome **bold** text")


class TestChemistry:
    """mhchem \\ce{...} notation."""

    def test_ce_command(self):
        assert has_latex("Water is \\ce{H2O}")

    def test_ce_reaction(self):
        assert has_latex("\\ce{CO2 + H2O -> H2CO3}")


class TestProtectRestore:
    """protect_latex() and restore_latex() round-trip preservation."""

    def test_no_latex_unchanged(self):
        text = "Plain text without math"
        protected, replacements = protect_latex(text)
        assert protected == text
        assert replacements == {}

    def test_display_math_preserved(self):
        text = "Before $$\\frac{a}{b}$$ after"
        protected, replacements = protect_latex(text)
        assert "$$" not in protected
        restored = restore_latex(protected, replacements)
        assert restored == text

    def test_inline_math_preserved(self):
        text = "The value $x^2$ is positive"
        protected, replacements = protect_latex(text)
        assert "$x^2$" not in protected
        restored = restore_latex(protected, replacements)
        assert restored == text

    def test_begin_align_preserved(self):
        text = "\\begin{align}\na &= b \\\\\nc &= d\n\\end{align}"
        protected, replacements = protect_latex(text)
        assert "\\begin{align}" not in protected
        restored = restore_latex(protected, replacements)
        assert restored == text

    def test_display_brackets_preserved(self):
        text = "\\[x^2 + y^2 = z^2\\]"
        protected, replacements = protect_latex(text)
        assert "\\[" not in protected
        restored = restore_latex(protected, replacements)
        assert restored == text

    def test_inline_parens_preserved(self):
        text = "Value \\(x + y\\) here"
        protected, replacements = protect_latex(text)
        assert "\\(" not in protected
        restored = restore_latex(protected, replacements)
        assert restored == text

    def test_chemistry_preserved(self):
        text = "Water is \\ce{H2O}"
        protected, replacements = protect_latex(text)
        assert "\\ce{" not in protected
        restored = restore_latex(protected, replacements)
        assert restored == text

    def test_mixed_content_preserved(self):
        text = "Inline $x^2$ and display $$y^2$$ and env \\begin{align}a\\end{align}"
        protected, replacements = protect_latex(text)
        restored = restore_latex(protected, replacements)
        assert restored == text

    def test_currency_not_protected(self):
        text = "The price is $50 and $100"
        protected, replacements = protect_latex(text)
        assert protected == text
        assert replacements == {}
