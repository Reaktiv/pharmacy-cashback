from apps.broadcasts.sanitizer import (
    plain_text_length,
    render_broadcast_message_html,
    sanitize_broadcast_html,
)


def test_allows_only_the_telegram_safe_tag_subset():
    result = sanitize_broadcast_html(
        "<b>bold</b> <i>italic</i> <u>under</u> <s>strike</s> <code>code</code>"
    )
    assert result == "<b>bold</b> <i>italic</i> <u>under</u> <s>strike</s> <code>code</code>"


def test_normalizes_common_aliases():
    assert sanitize_broadcast_html("<strong>x</strong>") == "<b>x</b>"
    assert sanitize_broadcast_html("<em>x</em>") == "<i>x</i>"
    assert sanitize_broadcast_html("<strike>x</strike>") == "<s>x</s>"
    assert sanitize_broadcast_html("<del>x</del>") == "<s>x</s>"


def test_strips_unknown_tags_but_keeps_their_text():
    assert sanitize_broadcast_html('<span style="color:red">hi</span>') == "hi"
    assert sanitize_broadcast_html("<h1>Title</h1>") == "Title"


def test_drops_script_and_style_content_entirely():
    assert sanitize_broadcast_html("<script>alert(1)</script>after") == "after"
    assert sanitize_broadcast_html("<style>.x{color:red}</style>after") == "after"


def test_only_http_and_https_links_survive_as_real_links():
    assert (
        sanitize_broadcast_html('<a href="https://example.com">go</a>')
        == '<a href="https://example.com">go</a>'
    )
    assert sanitize_broadcast_html('<a href="javascript:alert(1)">go</a>') == "go"
    assert sanitize_broadcast_html('<a href="data:text/html,x">go</a>') == "go"
    assert sanitize_broadcast_html("<a>no href</a>") == "no href"


def test_block_elements_become_line_breaks():
    assert sanitize_broadcast_html("<div>one</div><div>two</div>") == "one\ntwo"
    assert sanitize_broadcast_html("line1<br>line2") == "line1\nline2"


def test_collapses_excessive_blank_lines_and_trims_edges():
    assert sanitize_broadcast_html("<div><br></div><div>text</div><div><br></div>") == "text"


def test_escapes_stray_angle_brackets_in_plain_text():
    assert sanitize_broadcast_html("2 < 3 & 5 > 4") == "2 &lt; 3 &amp; 5 &gt; 4"


def test_unclosed_tags_are_still_closed_safely():
    assert sanitize_broadcast_html("<b>bold forever") == "<b>bold forever</b>"


def test_plain_text_length_ignores_tags_and_counts_utf16_units():
    assert plain_text_length("<b>hi</b>") == 2
    # An emoji outside the BMP counts as 2 UTF-16 units, same as Telegram.
    assert plain_text_length("a\U0001f600b") == 4


def test_render_broadcast_message_html_bolds_the_title_above_the_body():
    assert (
        render_broadcast_message_html("Sale!", "<b>20% off</b>")
        == "<b>Sale!</b>\n\n<b>20% off</b>"
    )
    assert render_broadcast_message_html("Sale!", "") == "<b>Sale!</b>"
    assert render_broadcast_message_html("", "body only") == "body only"


def test_render_broadcast_message_html_escapes_title():
    assert render_broadcast_message_html("A & B", "") == "<b>A &amp; B</b>"
