"""Paragraph-aware character chunks, bounded even for one enormous paragraph."""
import re


def chunk_text(text, size=900, overlap=120):
    if not 200 <= size <= 2000 or not 0 <= overlap < size // 2:
        raise ValueError('Choose chunk size 200..2000 and overlap less than half its size')
    text = text.replace('\r\n', '\n').strip()
    if not text or '\x00' in text:
        raise ValueError('Manual must contain non-empty UTF-8 text without NUL characters')
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundaries = [match.end() for match in re.finditer(r'\n\s*\n|[.!?]\s+|\s+', text[start:end])
                          if match.end() >= size // 2]
            if boundaries:
                end = start + boundaries[-1]
        value = text[start:end].strip()
        if value:
            chunks.append(value)
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks
