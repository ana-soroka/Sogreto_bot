"""
Утилиты форматирования текста для разных платформ.
VK не поддерживает Markdown — убираем разметку.
"""
import re


def markdown_to_plain(text: str) -> str:
    """Убрать Markdown-разметку из текста (для VK)."""
    if not text:
        return text
    # **bold** → bold
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    # *italic* → italic
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    # _italic_ → italic
    text = re.sub(r'_(.+?)_', r'\1', text)
    # `code` → code
    text = re.sub(r'`(.+?)`', r'\1', text)
    return text
