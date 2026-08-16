"""Input sanitization utilities (H52: XSS mitigation for stored content)."""

from __future__ import annotations

import html

import bleach


def sanitize_content(text: str | None) -> str:
    """Sanitize user-supplied text content stored in the knowledge base.

    Strips dangerous HTML tags and attributes while preserving safe markup.
    Falls back to HTML-entity escaping if bleach is unavailable.
    """
    if text is None:
        return ""
    # Allow common safe tags that users might intentionally include
    allowed_tags = frozenset(
        {
            "b",
            "i",
            "em",
            "strong",
            "u",
            "s",
            "code",
            "pre",
            "blockquote",
            "p",
            "br",
            "ul",
            "ol",
            "li",
            "a",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "table",
            "thead",
            "tbody",
            "tr",
            "th",
            "td",
            "hr",
            "img",
            "span",
            "div",
            "sup",
            "sub",
            "del",
            "ins",
            "mark",
        }
    )
    allowed_attrs = {
        "*": ["class", "id", "style"],
        "a": ["href", "title"],
        "img": ["alt", "src"],
    }
    return bleach.clean(
        text,
        tags=allowed_tags,
        attributes=allowed_attrs,
        strip=True,
    )
