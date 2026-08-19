"""taxonomy.yaml 로더 — 배치가 쓰는 최소한만 읽는다.

**감정 체계의 주인은 앱이다.** 분류·키워드 사전·문구는 전부 앱(JS)에서 쓰이고,
배치가 taxonomy에서 필요로 하는 것은 하나뿐이다 — **세분류 id 집합**.
themes.yaml의 mapping이 실제 감정 체계와 어긋나지 않는지 대조하는 데 쓴다
(themes.yaml 빌드 검증 1번).

그래서 여기서 감정 체계 전체를 객체로 만들지 않는다. 배치가 안 쓰는 것을
읽어 두면 언젠가 배치가 그걸 쓰기 시작하고, 그때부터 앱과 배치가 같은 사전을
두 벌로 해석하게 된다.
"""

from __future__ import annotations

from pathlib import Path

import yaml

EXPECTED_SUBCATEGORIES = 24


class TaxonomyError(ValueError):
    """taxonomy.yaml 구조 오류."""


def load_subcategory_ids(path: Path) -> set[str] | None:
    """세분류 id 집합. 파일이 없으면 None을 돌려준다.

    None은 "아직 이식되지 않았다"는 뜻이고, 호출부는 검증 1번을 건너뛴다.
    빈 집합과 구분해야 한다 — 빈 집합은 "파일은 있는데 세분류가 없다"이고
    그건 오류다.
    """
    if not path.exists():
        return None

    with path.open(encoding="utf-8") as fp:
        raw = yaml.safe_load(fp) or {}
    categories = raw.get("categories")
    if not isinstance(categories, list) or not categories:
        raise TaxonomyError(f"{path}: categories가 비어 있다")

    ids: set[str] = set()
    for category in categories:
        for sub in category.get("subcategories") or []:
            sub_id = str(sub.get("id", "")).strip()
            if not sub_id:
                raise TaxonomyError(f"{path}: id 없는 세분류가 있다 ({category.get('id')})")
            if sub_id in ids:
                raise TaxonomyError(f"{path}: 세분류 id 중복 — {sub_id}")
            ids.add(sub_id)

    if len(ids) != EXPECTED_SUBCATEGORIES:
        raise TaxonomyError(
            f"{path}: 세분류가 {len(ids)}개다 (기대 {EXPECTED_SUBCATEGORIES}개). "
            "themes.yaml mapping·media_defaults와 함께 고쳐야 한다"
        )
    return ids
