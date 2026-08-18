"""verses.yaml 읽기와 verified 필드 갱신.

**PyYAML로 덤프하지 않는다.** verses.yaml의 주석은 부산물이 아니라
큐레이션 자산이다 — 선정 근거, 검수 이력, 저작인격권 규칙, 감정 계열
구분선이 전부 주석에 있다. safe_load → safe_dump 한 번이면 전부 사라진다.

그래서 읽기는 PyYAML로 하되(구조 파악), 쓰기는 **라인 단위 in-place 편집**으로
한다. 건드리는 것은 verified / verified_by / verified_at 세 줄뿐이고,
text를 포함한 나머지 모든 바이트는 그대로 남는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

# 최상위 구절 항목의 시작. verses.yaml의 들여쓰기 규약(2칸 + "- ")을 따른다.
_ITEM_START = re.compile(r"^  - id:\s*(?P<id>\S+)\s*$")
# 항목 내부 필드. 들여쓰기 4칸.
_FIELD = re.compile(r"^    (?P<key>[A-Za-z_][A-Za-z0-9_]*):(?P<rest>.*)$")


class VersesFormatError(RuntimeError):
    """verses.yaml이 이 모듈이 가정한 형식과 다르다."""


@dataclass
class VerseBlock:
    """한 구절이 차지하는 라인 범위와 필드 위치."""

    verse_id: str
    start: int              # `  - id:` 라인 인덱스
    end: int                # 다음 항목 직전까지 (exclusive)
    fields: dict[str, int]  # 필드명 -> 라인 인덱스 (항목 직속 필드만)

    @property
    def last_field_line(self) -> int:
        return max(self.fields.values()) if self.fields else self.start


class VersesFile:
    """verses.yaml — 파싱 결과와 원본 라인을 함께 들고 있다."""

    def __init__(self, path: Path) -> None:
        self.path = path
        text = path.read_text(encoding="utf-8")
        self.lines: list[str] = text.splitlines()
        self._trailing_newline = text.endswith("\n")

        document = yaml.safe_load(text)
        if not isinstance(document, dict) or "verses" not in document:
            raise VersesFormatError(f"{path}: 최상위 'verses' 키가 없다")

        self.translation: str = document.get("translation", "")
        self.version: str = document.get("version", "")
        self.verses: list[dict] = document["verses"] or []
        self.blocks: dict[str, VerseBlock] = self._index_blocks()

        parsed_ids = [v["id"] for v in self.verses]
        missing = [i for i in parsed_ids if i not in self.blocks]
        if missing:
            raise VersesFormatError(
                f"{path}: 라인에서 찾지 못한 구절 id: {missing} "
                "(들여쓰기가 '  - id: ...' 규약과 다를 수 있다)"
            )

    def _index_blocks(self) -> dict[str, VerseBlock]:
        starts: list[tuple[int, str]] = []
        for index, line in enumerate(self.lines):
            match = _ITEM_START.match(line)
            if match:
                starts.append((index, match.group("id")))

        blocks: dict[str, VerseBlock] = {}
        for position, (start, verse_id) in enumerate(starts):
            end = starts[position + 1][0] if position + 1 < len(starts) else len(self.lines)
            fields: dict[str, int] = {}
            for index in range(start + 1, end):
                field = _FIELD.match(self.lines[index])
                if field:
                    fields[field.group("key")] = index
            if verse_id in blocks:
                raise VersesFormatError(f"중복된 구절 id: {verse_id}")
            blocks[verse_id] = VerseBlock(verse_id, start, end, fields)
        return blocks

    # -----------------------------------------------------------------
    # 갱신
    # -----------------------------------------------------------------
    def mark_verified(self, verse_id: str, verified_by: str, verified_at: str) -> None:
        """한 구절을 verified: true로 갱신하고 근거 필드를 채운다.

        verified 라인은 제자리에서 값만 바꾼다. verified_by / verified_at은
        있으면 값 교체, 없으면 verified 라인 바로 뒤에 삽입한다 — 항상
        verified → verified_by → verified_at 순서가 되도록.
        """
        block = self.blocks[verse_id]
        if "verified" not in block.fields:
            raise VersesFormatError(f"{verse_id}: verified 필드가 없다")

        self._set_field(verse_id, "verified", "true")
        anchor = self.blocks[verse_id].fields["verified"]
        anchor = self._set_or_insert(verse_id, "verified_by", verified_by, anchor)
        self._set_or_insert(verse_id, "verified_at", f'"{verified_at}"', anchor)

    def _set_field(self, verse_id: str, key: str, value: str) -> None:
        index = self.blocks[verse_id].fields[key]
        self.lines[index] = f"    {key}: {value}"

    def _set_or_insert(self, verse_id: str, key: str, value: str, anchor: int) -> int:
        block = self.blocks[verse_id]
        if key in block.fields:
            index = block.fields[key]
            self.lines[index] = f"    {key}: {value}"
            return index
        self.lines.insert(anchor + 1, f"    {key}: {value}")
        self._shift_after(anchor, 1)
        return anchor + 1

    def _shift_after(self, index: int, delta: int) -> None:
        """라인 삽입으로 밀린 인덱스를 모든 블록에서 보정한다."""
        for block in self.blocks.values():
            if block.start > index:
                block.start += delta
            if block.end > index:
                block.end += delta
            for key, line_no in list(block.fields.items()):
                if line_no > index:
                    block.fields[key] = line_no + delta

    def save(self) -> None:
        text = "\n".join(self.lines)
        if self._trailing_newline:
            text += "\n"
        self.path.write_text(text, encoding="utf-8", newline="\n")
