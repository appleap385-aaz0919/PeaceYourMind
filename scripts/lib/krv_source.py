"""개역한글(1961) 원문 데이터 로더와 구절 참조(ref) 파서.

원문 데이터의 출처·채택 근거는 data/krv/SOURCE.md 참조.
이 모듈은 원문을 **읽기만** 한다. 어떤 교정도 하지 않는다 (동일성유지권).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------
# 한글 책 이름 → 원문 데이터의 영문 키
#
# 정식 명칭과 대한성서공회 표준 약어를 모두 받는다. verses.yaml은 정식
# 명칭을 쓰지만(예: "베드로전서"), 약어("벧전")로 적힌 ref가 들어와도
# 조용히 실패하지 않고 해석되도록 한다.
# ---------------------------------------------------------------------
BOOK_KEYS: dict[str, str] = {}


def _register(english: str, *korean_names: str) -> None:
    for name in korean_names:
        BOOK_KEYS[name] = english


# 구약 39권
_register("Genesis", "창세기", "창")
_register("Exodus", "출애굽기", "출")
_register("Leviticus", "레위기", "레")
_register("Numbers", "민수기", "민")
_register("Deuteronomy", "신명기", "신")
_register("Joshua", "여호수아", "수")
_register("Judges", "사사기", "삿")
_register("Ruth", "룻기", "룻")
_register("1Samuel", "사무엘상", "삼상")
_register("2Samuel", "사무엘하", "삼하")
_register("1Kings", "열왕기상", "왕상")
_register("2Kings", "열왕기하", "왕하")
_register("1Chronicles", "역대상", "대상")
_register("2Chronicles", "역대하", "대하")
_register("Ezra", "에스라", "스")
_register("Nehemiah", "느헤미야", "느")
_register("Esther", "에스더", "에")
_register("Job", "욥기", "욥")
_register("Psalms", "시편", "시")
_register("Proverbs", "잠언", "잠")
_register("Ecclesiastes", "전도서", "전")
_register("SongofSolomon", "아가", "아")
_register("Isaiah", "이사야", "사")
_register("Jeremiah", "예레미야", "렘")
_register("Lamentations", "예레미야애가", "애")
_register("Ezekiel", "에스겔", "겔")
_register("Daniel", "다니엘", "단")
_register("Hosea", "호세아", "호")
_register("Joel", "요엘", "욜")
_register("Amos", "아모스", "암")
_register("Obadiah", "오바댜", "옵")
_register("Jonah", "요나", "욘")
_register("Micah", "미가", "미")
_register("Nahum", "나훔", "나")
_register("Habakkuk", "하박국", "합")
_register("Zephaniah", "스바냐", "습")
_register("Haggai", "학개", "학")
_register("Zechariah", "스가랴", "슥")
_register("Malachi", "말라기", "말")

# 신약 27권
_register("Matthew", "마태복음", "마")
_register("Mark", "마가복음", "막")
_register("Luke", "누가복음", "눅")
_register("John", "요한복음", "요")
_register("Acts", "사도행전", "행")
_register("Romans", "로마서", "롬")
_register("1Corinthians", "고린도전서", "고전")
_register("2Corinthians", "고린도후서", "고후")
_register("Galatians", "갈라디아서", "갈")
_register("Ephesians", "에베소서", "엡")
_register("Philippians", "빌립보서", "빌")
_register("Colossians", "골로새서", "골")
_register("1Thessalonians", "데살로니가전서", "살전")
_register("2Thessalonians", "데살로니가후서", "살후")
_register("1Timothy", "디모데전서", "딤전")
_register("2Timothy", "디모데후서", "딤후")
_register("Titus", "디도서", "딛")
_register("Philemon", "빌레몬서", "몬")
_register("Hebrews", "히브리서", "히")
_register("James", "야고보서", "약")
_register("1Peter", "베드로전서", "벧전")
_register("2Peter", "베드로후서", "벧후")
_register("1John", "요한일서", "요일")
_register("2John", "요한이서", "요이")
_register("3John", "요한삼서", "요삼")
_register("Jude", "유다서", "유")
_register("Revelation", "요한계시록", "계")


class RefError(ValueError):
    """ref 문자열을 해석할 수 없거나, 가리키는 절이 원문에 없다."""


@dataclass(frozen=True)
class VerseRef:
    """구절 참조 하나. 장을 넘는 범위(예: 시편 42:5-43:1)도 표현한다."""

    book_ko: str
    book_key: str
    start: tuple[int, int]  # (장, 절)
    end: tuple[int, int]

    @property
    def is_range(self) -> bool:
        return self.start != self.end


# "시편 42:5" / "빌립보서 4:6-7" / "시편 42:5-43:1"
_REF_PATTERN = re.compile(
    r"""^\s*
    (?P<book>.+?)\s+
    (?P<ch1>\d+):(?P<v1>\d+)
    (?:\s*[-–~]\s*(?:(?P<ch2>\d+):)?(?P<v2>\d+))?
    \s*$""",
    re.VERBOSE,
)


def parse_ref(ref: str) -> VerseRef:
    """'시편 46:1', '빌립보서 4:6-7', '시편 42:5-43:1' 형태를 해석한다."""
    match = _REF_PATTERN.match(ref)
    if not match:
        raise RefError(f"ref 형식을 해석할 수 없다: {ref!r}")

    book_ko = match.group("book").strip()
    book_key = BOOK_KEYS.get(book_ko)
    if book_key is None:
        raise RefError(f"알 수 없는 책 이름: {book_ko!r} (ref={ref!r})")

    ch1, v1 = int(match.group("ch1")), int(match.group("v1"))
    if match.group("v2") is None:
        ch2, v2 = ch1, v1
    else:
        ch2 = int(match.group("ch2")) if match.group("ch2") else ch1
        v2 = int(match.group("v2"))

    if (ch2, v2) < (ch1, v1):
        raise RefError(f"범위의 끝이 시작보다 앞선다: {ref!r}")

    return VerseRef(book_ko, book_key, (ch1, v1), (ch2, v2))


class KrvBible:
    """원문 전문. 절 단위 조회와 범위 조회를 제공한다."""

    def __init__(self, path: Path) -> None:
        self.path = path
        with path.open(encoding="utf-8") as handle:
            raw = json.load(handle)

        # (book_key, chapter) -> {verse_no: text},  그리고 장별 절 목록(순서 보존)
        self._verses: dict[tuple[str, int], dict[int, str]] = {}
        self._chapters: dict[str, list[int]] = {}
        for book in raw:
            key = book["book"]
            self._chapters[key] = [c["chapter"] for c in book["chapters"]]
            for chapter in book["chapters"]:
                self._verses[(key, chapter["chapter"])] = {
                    v["verse"]: v["text"] for v in chapter["verses"]
                }

    @property
    def verse_count(self) -> int:
        return sum(len(v) for v in self._verses.values())

    @property
    def book_count(self) -> int:
        return len(self._chapters)

    def verse(self, book_key: str, chapter: int, verse: int) -> str:
        try:
            return self._verses[(book_key, chapter)][verse]
        except KeyError as exc:
            raise RefError(f"원문에 없는 절: {book_key} {chapter}:{verse}") from exc

    def chapter_verses(self, book_key: str, chapter: int) -> list[tuple[int, str]]:
        """장 하나를 (절 번호, 본문) 목록으로 절 번호 순서대로 돌려준다.

        verses_in_range와 달리 **합본 구간을 거부하지 않는다.** 그쪽은 ref가
        가리키는 범위를 뽑는 경로라 같은 문장이 반복되면 수록하면 안 되지만,
        이쪽은 "이어서 읽기"가 장 전체를 그대로 보여주는 경로다. 합본 구간을
        여기서 막으면 시편 92편·이사야 30편이 통째로 열리지 않는다.
        반복을 어떻게 보일지는 화면의 판단이고(절 번호를 묶어 한 번만 그린다),
        데이터를 내주는 이 자리에서 할 일이 아니다.
        """
        verses = self._verses.get((book_key, chapter))
        if verses is None:
            raise RefError(f"원문에 없는 장: {book_key} {chapter}")
        return [(number, verses[number]) for number in sorted(verses)]

    def verses_in_range(self, ref: VerseRef) -> list[tuple[int, int, str]]:
        """범위에 든 절을 (장, 절, 본문) 순서대로 돌려준다.

        범위 안에 실제로 없는 절이 있으면 RefError — 절 경계가 틀린 ref를
        조용히 넘기지 않기 위해서다. (verses.yaml 시편 46:1 사례 참조)
        """
        (ch1, v1), (ch2, v2) = ref.start, ref.end
        chapters = self._chapters.get(ref.book_key)
        if chapters is None:
            raise RefError(f"원문에 없는 책: {ref.book_key}")

        out: list[tuple[int, int, str]] = []
        for chapter in range(ch1, ch2 + 1):
            verses = self._verses.get((ref.book_key, chapter))
            if verses is None:
                raise RefError(f"원문에 없는 장: {ref.book_ko} {chapter}장")
            first = v1 if chapter == ch1 else 1
            last = v2 if chapter == ch2 else max(verses)
            for number in range(first, last + 1):
                if number not in verses:
                    raise RefError(
                        f"원문에 없는 절: {ref.book_ko} {chapter}:{number}"
                    )
                out.append((chapter, number, verses[number]))

        if not out:
            raise RefError(f"범위가 비어 있다: {ref.book_ko}")

        # 절 합본 구간 방어 — 원문이 여러 절을 하나로 묶어 제시하는 곳이 있다.
        #
        # 개역한글은 시편 92:1-3처럼 여러 절을 나누지 않고 합쳐 싣는 구간이
        # 있고(대한성서공회 사이트도 "1-3"으로 표시한다), 데이터는 그 합본
        # 본문을 각 절 번호에 똑같이 복제해 절 수(31,102)를 맞춘다.
        #
        # 그래서 그런 구간을 범위로 조회하면 같은 문장이 2~3번 반복된 본문이
        # 나온다. 조용히 통과시키면 중복된 본문이 그대로 수록된다.
        # 전체 66권에 19개 구간이 있다 (시편 92:1-3, 렘 32:3-5 등).
        #
        # 단일 절 조회는 안전하다 — 합본 전체가 그 절에 들어 있다. 다만 그
        # 경우 ref가 가리키는 범위와 본문 내용이 어긋나므로, 이런 구간은
        # 수록 대상에서 빼는 편이 낫다.
        texts = [text for _, _, text in out]
        if len(texts) > 1 and len(set(texts)) < len(texts):
            raise RefError(
                f"절 합본 구간이다: {ref.book_ko} — 같은 본문이 여러 절 번호에 "
                "중복돼 있어 범위로 쓰면 문장이 반복된다. 이 구간은 수록하지 않는다."
            )
        return out


_WHITESPACE = re.compile(r"\s+")


def normalize_ws(text: str) -> str:
    """공백·개행 정규화. 연속 공백을 1개로 줄이고 양끝을 다듬는다.

    **이것이 허용되는 차이의 전부다.** 맞춤법·조사·어미는 한 글자도
    다르면 불일치다 (동일성유지권 — verses.yaml 헤더 참조).

    YAML 폴디드 스칼라(`>`)가 줄바꿈을 공백으로 바꾸고 끝에 개행을 붙이므로,
    소스 쪽 정규화는 필수다. 원문 쪽에도 같은 규칙을 적용해 비교를 대칭으로 둔다.
    """
    return _WHITESPACE.sub(" ", text).strip()
