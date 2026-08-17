from ui_sidebar import get_preview_html_source, has_summary_content


def test_get_preview_html_source_prefers_summary_html():
    messages = [{"role": "assistant", "content": "```html\n<html>legacy</html>\n```"}]
    summary_html = "<html><body>summary</body></html>"

    assert get_preview_html_source(messages, summary_html) == summary_html


def test_has_summary_content_accepts_first_user_message():
    messages = [{"role": "user", "content": "첫 번째 질문입니다."}]

    assert has_summary_content(messages) is True
