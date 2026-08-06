"""Server-side, authoritative HTML sanitizer for broadcast bodies.

Never trust client-produced HTML — user-entered rich text must be converted
to Telegram's safe HTML subset before it's ever stored or sent, never passed
through raw. Telegram's Bot API only understands a tiny formatting subset
under `parse_mode="HTML"`: `<b>`, `<i>`, `<u>`, `<s>`, `<code>`, `<pre>`,
`<a href="">`. Everything else from a browser's contentEditable output
(spans, divs, style attributes, stray markup) is either normalized onto one
of those tags (`strong`->`b`, `em`->`i`, `strike`/`del`->`s`, `br`/`div`/`p`
-> a line break) or stripped down to its inner text.

Only stdlib is used here (CLAUDE.md §9: ask before adding a dependency) —
no bleach/nh3/lxml.
"""

import re
from html import escape as _escape
from html.parser import HTMLParser
from urllib.parse import urlparse

ALLOWED_TAGS = {"b", "i", "u", "s", "code", "pre", "a"}
TAG_ALIASES = {"strong": "b", "em": "i", "strike": "s", "del": "s"}
BLOCK_TAGS = {"div", "p", "br", "li", "tr"}
# Their *content* is discarded outright, not just unwrapped — unlike an
# unknown tag (e.g. <span>), text inside these was never meant to be read.
DROP_CONTENT_TAGS = {"script", "style"}

_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def _is_safe_href(href: str) -> bool:
    try:
        parsed = urlparse(href)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class _TelegramHTMLSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.open_stack: list[str] = []
        self.drop_depth = 0  # >0 while inside a <script>/<style> we're discarding

    def handle_starttag(self, tag, attrs):
        self._handle_open(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag, attrs):
        self._handle_open(tag, attrs, self_closing=True)

    def _handle_open(self, tag, attrs, *, self_closing):
        tag = tag.lower()
        if tag in DROP_CONTENT_TAGS:
            if not self_closing:
                self.drop_depth += 1
            return
        if self.drop_depth:
            return
        if tag in BLOCK_TAGS:
            self._newline()
            return
        canonical = TAG_ALIASES.get(tag, tag)
        if canonical not in ALLOWED_TAGS:
            return  # unsupported tag: drop the tag itself, keep its children
        if canonical == "a":
            href = dict(attrs).get("href") or ""
            if not _is_safe_href(href):
                return  # not a real http(s) link — render as plain text
            self.out.append(f'<a href="{_escape(href, quote=True)}">')
            self.open_stack.append("a")
        else:
            self.out.append(f"<{canonical}>")
            self.open_stack.append(canonical)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in DROP_CONTENT_TAGS:
            if self.drop_depth:
                self.drop_depth -= 1
            return
        if self.drop_depth or tag in BLOCK_TAGS:
            return
        canonical = TAG_ALIASES.get(tag, tag)
        if canonical not in ALLOWED_TAGS or canonical not in self.open_stack:
            return  # never emit an orphan closing tag
        # Close back to (and including) the matching tag — tolerates
        # overlapping/mismatched nesting from imperfect editor output.
        while self.open_stack:
            top = self.open_stack.pop()
            self.out.append(f"</{top}>")
            if top == canonical:
                break

    def handle_data(self, data):
        if not self.drop_depth:
            self.out.append(_escape(data))

    def _newline(self):
        if self.out and not self.out[-1].endswith("\n"):
            self.out.append("\n")

    def close_all(self):
        while self.open_stack:
            self.out.append(f"</{self.open_stack.pop()}>")

    def result(self) -> str:
        return "".join(self.out)


def sanitize_broadcast_html(raw_html: str) -> str:
    """Convert arbitrary editor HTML into Telegram's safe subset. Collapses
    3+ consecutive newlines down to one blank line and trims surrounding
    whitespace, so a stray empty leading/trailing editor line doesn't
    become dead space in the actual Telegram message."""
    parser = _TelegramHTMLSanitizer()
    parser.feed(raw_html or "")
    parser.close()
    parser.close_all()
    text = _MULTI_NEWLINE_RE.sub("\n\n", parser.result())
    return text.strip("\n")


class _PlainTextExtractor(HTMLParser):
    """Pulls out only the visible text of already-sanitized HTML — used to
    measure length against Telegram's real limit, which counts rendered
    text and never the formatting tags themselves."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_data(self, data):
        self._parts.append(data)

    def result(self) -> str:
        return "".join(self._parts)


def plain_text_length(html: str) -> int:
    """Telegram counts UTF-16 code units, not Python codepoints — this
    matters for anything outside the Basic Multilingual Plane (most emoji),
    which a promotional broadcast is likely to contain."""
    extractor = _PlainTextExtractor()
    extractor.feed(html or "")
    extractor.close()
    return len(extractor.result().encode("utf-16-le")) // 2


def render_broadcast_message_html(title: str, body_html: str) -> str:
    """The exact HTML actually sent to Telegram — used both to measure a
    broadcast's length against Telegram's limit (BroadcastSerializer) and to
    build the real outgoing text/caption (apps.broadcasts.tasks), so the two
    can never drift apart. `title` is always plain text (escaped here, never
    run through sanitize_broadcast_html — only the composer body is rich
    text) and rendered bold above the body."""
    header = f"<b>{_escape(title)}</b>" if title else ""
    if header and body_html:
        return f"{header}\n\n{body_html}"
    return header or body_html
