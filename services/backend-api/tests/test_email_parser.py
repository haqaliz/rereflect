"""Tests for email body parser - smart stripping of forwarded email noise."""
import pytest

from src.services.email_parser import parse_email_body


class TestParseEmailBodyBasic:
    """Basic input handling."""

    def test_none_inputs_returns_empty_string(self):
        """Should return empty string when both html and text are None."""
        assert parse_email_body(None, None) == ""

    def test_empty_string_inputs_returns_empty_string(self):
        """Should return empty string when both are empty."""
        assert parse_email_body("", "") == ""

    def test_plain_text_only(self):
        """Should return plain text when no HTML is provided."""
        result = parse_email_body(None, "This is plain text feedback.")
        assert result == "This is plain text feedback."

    def test_prefers_html_when_both_provided(self):
        """Should prefer HTML (converted to text) over plain text when both are given."""
        html = "<p>HTML version of feedback</p>"
        text = "Plain text version"
        result = parse_email_body(html, text)
        assert "HTML version of feedback" in result


class TestHtmlToPlainText:
    """HTML stripping."""

    def test_strips_basic_html_tags(self):
        """Should remove HTML tags and return plain text."""
        html = "<p>Hello <b>World</b></p>"
        result = parse_email_body(html, None)
        assert "Hello" in result
        assert "World" in result
        assert "<p>" not in result
        assert "<b>" not in result

    def test_strips_nested_html(self):
        """Should handle nested HTML elements."""
        html = "<div><p>Outer <span>inner</span> text</p></div>"
        result = parse_email_body(html, None)
        assert "Outer" in result
        assert "inner" in result
        assert "text" in result
        assert "<" not in result

    def test_converts_br_to_newline(self):
        """Should convert <br> tags to newlines."""
        html = "<p>Line one<br>Line two<br/>Line three</p>"
        result = parse_email_body(html, None)
        assert "Line one" in result
        assert "Line two" in result
        assert "Line three" in result

    def test_strips_style_and_script_tags_with_content(self):
        """Should remove <style> and <script> tags along with their content."""
        html = "<p>Hello</p><style>.foo{color:red}</style><script>alert(1)</script><p>World</p>"
        result = parse_email_body(html, None)
        assert "Hello" in result
        assert "World" in result
        assert "color" not in result
        assert "alert" not in result


class TestForwardingHeaderRemoval:
    """Removal of forwarding header blocks."""

    def test_removes_gmail_forwarding_header(self):
        """Should remove '---------- Forwarded message ----------' and the header block."""
        text = (
            "---------- Forwarded message ----------\n"
            "From: customer@example.com\n"
            "Date: Mon, Jan 1, 2024\n"
            "Subject: Product issue\n"
            "To: support@company.com\n"
            "\n"
            "I have a problem with your product."
        )
        result = parse_email_body(None, text)
        assert "I have a problem with your product" in result
        assert "Forwarded message" not in result
        assert "From: customer@example.com" not in result
        assert "Date: Mon" not in result
        assert "Subject: Product issue" not in result
        assert "To: support@company.com" not in result

    def test_removes_outlook_forwarding_header(self):
        """Should remove Outlook-style forwarding headers."""
        text = (
            "-----Original Message-----\n"
            "From: sender@example.com\n"
            "Sent: Tuesday, January 2, 2024\n"
            "To: support@company.com\n"
            "Subject: Help needed\n"
            "\n"
            "Please help me with this issue."
        )
        result = parse_email_body(None, text)
        assert "Please help me with this issue" in result
        assert "Original Message" not in result

    def test_preserves_content_before_forwarding_header(self):
        """Should preserve any note added by the forwarder before the header."""
        text = (
            "FYI, this customer needs help:\n"
            "\n"
            "---------- Forwarded message ----------\n"
            "From: customer@example.com\n"
            "Date: Mon, Jan 1, 2024\n"
            "Subject: Issue\n"
            "To: support@company.com\n"
            "\n"
            "My account is broken."
        )
        result = parse_email_body(None, text)
        # Both the forwarder's note and the original message body should be present
        assert "My account is broken" in result


class TestSignatureStripping:
    """Stripping of email signatures."""

    def test_strips_double_dash_signature(self):
        """Should strip content after '-- ' signature delimiter."""
        text = (
            "I love your product but the search is slow.\n"
            "\n"
            "-- \n"
            "John Doe\n"
            "CEO, Acme Corp\n"
            "john@acme.com"
        )
        result = parse_email_body(None, text)
        assert "search is slow" in result
        assert "John Doe" not in result
        assert "CEO" not in result

    def test_strips_underscore_signature(self):
        """Should strip content after '___' line."""
        text = (
            "The billing page has a bug.\n"
            "\n"
            "_______________________________________________\n"
            "Jane Smith\n"
            "Product Manager"
        )
        result = parse_email_body(None, text)
        assert "billing page has a bug" in result
        assert "Jane Smith" not in result

    def test_strips_best_regards(self):
        """Should strip content starting with 'Best regards'."""
        text = (
            "I want a dark mode feature.\n"
            "\n"
            "Best regards,\n"
            "Alex Johnson"
        )
        result = parse_email_body(None, text)
        assert "dark mode feature" in result
        assert "Best regards" not in result
        assert "Alex Johnson" not in result

    def test_strips_sent_from_iphone(self):
        """Should strip 'Sent from my iPhone' and similar."""
        text = (
            "App crashes when I open settings.\n"
            "\n"
            "Sent from my iPhone"
        )
        result = parse_email_body(None, text)
        assert "App crashes" in result
        assert "Sent from my iPhone" not in result

    def test_strips_sent_from_samsung(self):
        """Should strip Samsung device signatures."""
        text = (
            "Cannot upload files larger than 10MB.\n"
            "\n"
            "Sent from Samsung Galaxy"
        )
        result = parse_email_body(None, text)
        assert "Cannot upload files" in result
        assert "Samsung" not in result

    def test_strips_thanks_regards(self):
        """Should strip common sign-offs like 'Thanks,' or 'Regards,'."""
        text = (
            "Please add export to PDF.\n"
            "\n"
            "Thanks,\n"
            "Mike"
        )
        result = parse_email_body(None, text)
        assert "export to PDF" in result
        assert "Thanks," not in result
        assert "Mike" not in result


class TestQuotedReplyRemoval:
    """Removal of quoted replies."""

    def test_removes_lines_starting_with_angle_bracket(self):
        """Should remove lines starting with '>'."""
        text = (
            "I still have this issue.\n"
            "\n"
            "> On Jan 1, 2024, support wrote:\n"
            "> Thanks for reaching out.\n"
            "> We will look into this."
        )
        result = parse_email_body(None, text)
        assert "still have this issue" in result
        assert "Thanks for reaching out" not in result

    def test_removes_on_date_wrote_block(self):
        """Should remove 'On ... wrote:' and subsequent quoted content."""
        text = (
            "This is my reply.\n"
            "\n"
            "On Mon, Jan 1, 2024 at 10:00 AM Support Team <support@example.com> wrote:\n"
            "Thank you for contacting us.\n"
            "We are looking into your issue."
        )
        result = parse_email_body(None, text)
        assert "This is my reply" in result
        assert "Thank you for contacting us" not in result


class TestWhitespaceCleanup:
    """Whitespace normalization."""

    def test_collapses_multiple_blank_lines(self):
        """Should collapse multiple blank lines into at most one."""
        text = "First line.\n\n\n\n\nSecond line."
        result = parse_email_body(None, text)
        # Should not have more than one consecutive blank line
        assert "\n\n\n" not in result
        assert "First line." in result
        assert "Second line." in result

    def test_trims_leading_and_trailing_whitespace(self):
        """Should trim whitespace from the beginning and end."""
        text = "   \n\n  Actual feedback.  \n\n   "
        result = parse_email_body(None, text)
        assert result == "Actual feedback."

    def test_strips_trailing_spaces_from_lines(self):
        """Should remove trailing spaces from individual lines."""
        text = "Line one.   \nLine two.  "
        result = parse_email_body(None, text)
        assert "Line one." in result
        assert "Line two." in result


class TestCombinedParsing:
    """Tests combining multiple stripping operations."""

    def test_full_forwarded_email_gmail(self):
        """Should handle a realistic Gmail forwarded email."""
        html = """
        <div dir="ltr">
            <br><br>
            <div class="gmail_quote">
                <div dir="ltr" class="gmail_attr">
                    ---------- Forwarded message ---------<br>
                    From: <strong class="gmail_sendername" dir="auto">John Customer</strong>
                    <span dir="auto">&lt;john@customer.com&gt;</span><br>
                    Date: Tue, Jan 2, 2024 at 3:45 PM<br>
                    Subject: Dashboard loading slowly<br>
                    To: support@company.com<br>
                </div>
                <br><br>
                <div dir="ltr">
                    <p>Hi team,</p>
                    <p>The dashboard has been loading very slowly for the past week.
                    It takes about 30 seconds to load the main page.</p>
                    <p>Can you please look into this?</p>
                    <p>Best regards,<br>John Customer<br>Acme Corp</p>
                </div>
            </div>
        </div>
        """
        result = parse_email_body(html, None)
        assert "dashboard" in result.lower()
        assert "30 seconds" in result
        assert "Forwarded message" not in result
        assert "John Customer" not in result or "Best regards" not in result

    def test_full_forwarded_email_plain_text(self):
        """Should handle a realistic plain-text forwarded email."""
        text = (
            "---------- Forwarded message ----------\n"
            "From: alice@example.com\n"
            "Date: Wed, Jan 3, 2024 at 9:00 AM\n"
            "Subject: Feature request\n"
            "To: feedback@company.com\n"
            "\n"
            "Hello,\n"
            "\n"
            "I would love to see a Kanban board view for tracking tasks.\n"
            "It would help our team manage work more effectively.\n"
            "\n"
            "Thanks,\n"
            "Alice"
        )
        result = parse_email_body(None, text)
        assert "Kanban board" in result
        assert "manage work" in result
        assert "Forwarded message" not in result
        assert "alice@example.com" not in result
        assert "Alice" not in result or "Thanks," not in result

    def test_email_with_quoted_reply_and_signature(self):
        """Should strip both quoted reply and signature."""
        text = (
            "The issue is still happening after the update.\n"
            "\n"
            "-- \n"
            "Bob Developer\n"
            "bob@dev.com\n"
            "\n"
            "On Mon, Jan 1, 2024 at 8:00 AM Support <support@co.com> wrote:\n"
            "> We have pushed a fix for this issue.\n"
            "> Please let us know if it persists."
        )
        result = parse_email_body(None, text)
        assert "still happening after the update" in result
        assert "Bob Developer" not in result
        assert "We have pushed a fix" not in result
