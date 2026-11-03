"""추천 로직. UI(Streamlit)에 의존하지 않는다."""
import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

CUISINES = ["한식", "일식", "중식", "서양식", "기타"]
DIFFICULTIES = ["쉬움", "보통", "어려움"]


def load_recipes() -> list[dict]:
    """data/recipes.json에서 레시피 목록을 읽어 반환한다."""
    with open(DATA_DIR / "recipes.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_staples() -> frozenset[str]:
    """기본 양념 목록(data/staples.json)."""
    with open(DATA_DIR / "staples.json", encoding="utf-8") as f:
        return frozenset(json.load(f))


def _passes_filters(recipe: dict, f: dict) -> bool:
    """일치율과 무관한 필터(요리 종류, 시간, 난이도, 제외 재료)를 통과하는지 검사한다."""
    if f.get("cuisines") is not None and recipe["cuisine"] not in f["cuisines"]:
        return False
    if f.get("max_time") is not None and recipe["time_min"] > f["max_time"]:
        return False
    if f.get("difficulties") is not None and recipe["difficulty"] not in f["difficulties"]:
        return False
    excluded = set(f.get("exclude") or [])
    if excluded and any(i["name"] in excluded for i in recipe["ingredients"]):
        return False
    return True


def _score_all(user_ings: list[str], filters: dict | None, recipes: list[dict] | None) -> list[dict]:
    """필터를 통과한 레시피를 일치율 순으로 정렬해 반환한다(일치율 0 제외, 임계값 미적용)."""
    f = filters or {}
    if not user_ings:
        return []
    typed = set(user_ings)
    owned = set(typed)
    if f.get("staples_owned"):
        owned |= load_staples()

    scored = []
    for recipe in recipes if recipes is not None else load_recipes():
        if not _passes_filters(recipe, f):
            continue
        required = [i["name"] for i in recipe["ingredients"] if i["required"]]
        if not required:
            continue
        have = [n for n in required if n in owned]
        # 기본 양념 가정만으로 매칭되는 요리는 제외: 사용자가 고른 재료가 하나라도 쓰여야 한다
        if not any(n in typed for n in required):
            continue
        all_names = {i["name"] for i in recipe["ingredients"]}
        scored.append({
            "recipe": recipe,
            "match_rate": len(have) / len(required),
            "have": have,
            "missing": [n for n in required if n not in owned],
            # 기본 양념 가정으로 채워진 필수 재료(사용자가 입력하지 않은 것)
            "assumed": [n for n in have if n not in typed],
            # 이 레시피가 쓰는 '사용자 입력 재료' 수(필수+선택 재료 모두 포함)
            "used": len(typed & all_names),
            "ingredients": [
                {"name": i["name"], "amount": i["amount"], "required": i["required"],
                 "owned": i["name"] in owned, "assumed": i["name"] in owned and i["name"] not in typed}
                for i in recipe["ingredients"]
            ],
        })
    # 일치율 → 부족 재료 적은 순(PRD F10) → 내 재료를 더 많이 쓰는 순 → 이름
    scored.sort(key=lambda r: (-r["match_rate"], len(r["missing"]), -r["used"], r["recipe"]["name"]))
    return scored


def recommend(user_ings: list[str], filters: dict | None = None, top_n: int = 10,
              recipes: list[dict] | None = None) -> list[dict]:
    """보유 재료로 만들 수 있는 요리를 일치율 순으로 추천한다.

    Args:
        user_ings: 정규화된 보유 재료 리스트.
        filters: 선택 필터 dict. 모든 키는 생략 가능.
            cuisines(list|None): 허용 요리 종류, None이면 전체.
            max_time(int|None): 최대 조리 시간(분).
            difficulties(list|None): 허용 난이도.
            exclude(list): 포함되면 제외할 재료(필수/선택 모두 검사).
            staples_owned(bool): True면 기본 양념을 보유한 것으로 간주.
            min_rate(float): 최소 일치율(0~1).
        top_n: 반환할 최대 개수.
        recipes: 레시피 목록. 생략하면 파일에서 읽는다(캐싱된 목록을 넘길 때 사용).

    Returns:
        {"recipe", "match_rate"(0~1), "have", "missing", "assumed", "used", "ingredients"} dict의 리스트.
        일치율 내림차순, 동률이면 부족 재료가 적은 순, 그다음 내 재료를 더 많이 쓰는 순.
    """
    min_rate = (filters or {}).get("min_rate", 0.0)
    scored = [r for r in _score_all(user_ings, filters, recipes) if r["match_rate"] >= min_rate]
    return scored[:max(top_n, 0)]


def recommend_with_fallback(user_ings: list[str], filters: dict | None = None, top_n: int = 10,
                            fallback_n: int = 3, recipes: list[dict] | None = None) -> tuple[list[dict], bool]:
    """recommend와 같지만, 임계값을 통과한 요리가 없으면 가장 근접한 요리 fallback_n개를 반환한다.

    Returns:
        (결과 리스트, 근접 요리 대체 여부). 필터(종류/시간/난이도/제외)까지 통과한 요리가
        하나도 없거나 재료가 비어 있으면 ([], False).
    """
    results = recommend(user_ings, filters, top_n, recipes)
    if results:
        return results, False
    closest = _score_all(user_ings, filters, recipes)[:fallback_n]
    return closest, bool(closest)
