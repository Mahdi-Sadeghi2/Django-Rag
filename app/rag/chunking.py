from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models import Chunk


@dataclass
class Heading:
    level: int
    text: str


@dataclass
class ChunkWithHeading:
    content: str
    heading_path: str


def split_by_headings(content: str) -> list[tuple[str, str]]:
    """متن را بر اساس سرفصل‌های markdown (# ...) به بخش‌ها می‌شکند.

    خروجی: لیستی از (heading_path, section_text)
    """
    lines = content.split("\n")
    sections: list[tuple[str, str]] = []
    current_path: list[str] = []   # سلسله‌مراتب سرفصل‌ها
    current_lines: list[str] = []

    def flush() -> None:
        text = "\n".join(current_lines).strip()
        if text:
            sections.append((" > ".join(current_path), text))
        current_lines.clear()

    for line in lines:
        m = re.match(r"^(#{1,4}) (.+)$", line)
        if m:
            flush()
            level = len(m.group(1))
            # سلسله‌مراتب را تا سطح جدید برش بزن
            current_path = current_path[: level - 1]
            current_path.append(m.group(2).strip())
        else:
            current_lines.append(line)
    flush()

    return sections


def chunk_section(
    text: str,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[str]:
    """یک بخش را به تکه‌های حداکثر max_chars می‌شکند، با هم‌پوشانی.

    - پاراگراف‌ها (بلوک‌های خالی‌جدا) واحد اصلی‌اند؛ کد نمونه هرگز وسطش قطع نمی‌شود
      مگر اینکه خودش از max_chars بزرگ‌تر باشد.
    - overlap فقط در مرز پاراگراف اعمال می‌شود تا کد و جمله بریده نشوند.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        plen = len(para)
        if plen > max_chars:
            # پاراگراف بزرگ (معمولاً code block): اول تکه‌های قبلی را flush کن
            if current:
                chunks.append("\n\n".join(current))
                current, current_len = [], 0
            # بعد خودش را با پنجره‌ی لغزان بشکن
            step = max_chars - overlap_chars
            for i in range(0, plen, step):
                chunks.append(para[i: i + max_chars])
            continue

        if current_len + plen + 2 > max_chars and current:
            chunks.append("\n\n".join(current))
            # overlap: پاراگراف‌های آخر را برای تکه‌ی بعد نگه دار
            tail: list[str] = []
            tail_len = 0
            for p in reversed(current):
                if tail_len + len(p) + 2 > overlap_chars:
                    break
                tail.insert(0, p)
                tail_len += len(p) + 2
            current = tail
            current_len = tail_len

        current.append(para)
        current_len += plen + 2

    if current:
        chunks.append("\n\n".join(current))

    return chunks
