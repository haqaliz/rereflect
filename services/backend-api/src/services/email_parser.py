"""Smart email body parsing for inbound email feedback.

Strips forwarding headers, signatures, quoted replies, and HTML
to extract clean feedback text from forwarded emails.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Optional


class _HTMLTextExtractor(HTMLParser):
    """Extract plain text from HTML, converting <br> to newlines and skipping scripts/styles."""

    SKIP_TAGS = {"script", "style", "head"}

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth += 1
        if tag.lower() in ("br", "p", "div", "tr", "li"):
            self._parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag.lower() in ("p", "div", "tr", "li"):
            self._parts.append("\n")

    def handle_data(self, data: str):
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def _html_to_text(html: str) -> str:
    """Convert HTML to plain text."""
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    return extractor.get_text()


# Forwarding header patterns (allow leading whitespace from HTML conversion)
_FORWARDING_DELIMITERS = [
    re.compile(r"^\s*-{3,}\s*Forwarded message\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*-{3,}\s*Original Message\s*-{3,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*Begin forwarded message\s*:", re.IGNORECASE | re.MULTILINE),
]

# Header lines that follow forwarding delimiters (From:, Date:, Subject:, To:, Sent:, Cc:)
_HEADER_LINE = re.compile(r"^(From|Date|Subject|To|Sent|Cc|Bcc):\s*.*$", re.IGNORECASE | re.MULTILINE)

# Signature patterns (lines that start a signature block)
_SIGNATURE_PATTERNS = [
    re.compile(r"^-- $", re.MULTILINE),                           # standard sig delimiter
    re.compile(r"^--\s*$", re.MULTILINE),                         # -- with optional space
    re.compile(r"^_{3,}", re.MULTILINE),                          # ___...
    re.compile(r"^Best regards[,.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Kind regards[,.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Thanks[,.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Thank you[,.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Regards[,.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Cheers[,.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Sent from my (iPhone|iPad|Galaxy|Samsung|Android|Pixel)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Sent from Samsung", re.IGNORECASE | re.MULTILINE),
]

# Quoted reply patterns
_ON_WROTE_PATTERN = re.compile(
    r"^On\s+.+\s+wrote:\s*$", re.IGNORECASE | re.MULTILINE
)


def _remove_forwarding_headers(text: str) -> str:
    """Remove forwarding delimiter and the header block that follows it.

    Handles indented headers (common after HTML-to-text conversion) and
    continuation lines (e.g. multi-line From: with email on next line).
    """
    for pattern in _FORWARDING_DELIMITERS:
        match = pattern.search(text)
        if match:
            before = text[:match.start()]
            after = text[match.end():]
            # Strip header lines from the remaining text
            lines = after.split("\n")
            body_start = 0
            found_header = False
            last_was_header = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped == "":
                    if found_header:
                        last_was_header = False
                    # Skip blank lines in the header block
                    continue
                if _HEADER_LINE.match(stripped):
                    found_header = True
                    last_was_header = True
                    continue
                if found_header and last_was_header and not _HEADER_LINE.match(stripped):
                    # Could be a continuation line (e.g. "<email@example.com>")
                    # or indented content that's part of the header block.
                    # Check if next non-empty line is a header to decide.
                    looks_like_continuation = (
                        stripped.startswith("<") or stripped.startswith("&lt;")
                    )
                    if looks_like_continuation:
                        continue
                    # Check if any upcoming line is still a header
                    next_header = False
                    for j in range(i + 1, min(i + 4, len(lines))):
                        ns = lines[j].strip()
                        if ns and _HEADER_LINE.match(ns):
                            next_header = True
                            break
                    if next_header:
                        # This is a non-header line in the middle of header block, skip
                        continue
                    # This is the start of the body
                    body_start = i
                    break
                if not found_header:
                    # Haven't found any header yet, skip non-empty non-header lines
                    continue
                # found_header is True but last_was_header is False: body starts here
                body_start = i
                break
            else:
                body_start = len(lines)

            body = "\n".join(lines[body_start:])
            text = before + "\n" + body

    return text


def _remove_signatures(text: str) -> str:
    """Remove email signatures from the end of the text."""
    lines = text.split("\n")
    cut_index = len(lines)

    for i, line in enumerate(lines):
        for pattern in _SIGNATURE_PATTERNS:
            if pattern.match(line):
                cut_index = i
                return "\n".join(lines[:cut_index])

    return text


def _remove_quoted_replies(text: str) -> str:
    """Remove quoted reply blocks (lines starting with > or 'On ... wrote:' blocks)."""
    # First, find "On ... wrote:" and remove everything from that line onward
    match = _ON_WROTE_PATTERN.search(text)
    if match:
        text = text[:match.start()]

    # Remove remaining lines starting with >
    lines = text.split("\n")
    cleaned = [line for line in lines if not line.strip().startswith(">")]
    return "\n".join(cleaned)


def _cleanup_whitespace(text: str) -> str:
    """Collapse multiple blank lines and trim."""
    # Strip trailing spaces from each line
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    # Collapse 3+ consecutive newlines to 2 (one blank line)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_email_body(html: Optional[str], text: Optional[str]) -> str:
    """Parse email body, stripping noise from forwarded emails.

    Args:
        html: HTML body of the email (preferred if available).
        text: Plain text body of the email (fallback).

    Returns:
        Cleaned plain text suitable for feedback analysis.
    """
    # Choose source: prefer HTML, fall back to plain text
    if html and html.strip():
        raw = _html_to_text(html)
    elif text and text.strip():
        raw = text
    else:
        return ""

    # Apply stripping pipeline
    result = _remove_forwarding_headers(raw)
    result = _remove_quoted_replies(result)
    result = _remove_signatures(result)
    result = _cleanup_whitespace(result)
    return result
