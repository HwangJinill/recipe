"""입력 파싱과 재료 정규화 유틸리티."""
import json
import re
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

MAX_ITEMS = 30        # 한 번에 처리할 최대 재료 수
MAX_TOKEN_LEN = 20    # 재료 이름 최대 길이


def _load_json(name: str):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_synonyms() -> dict[str, str]:
    """동의어 사전(data/synonyms.json)."""
    return _load_json("synonyms.json")


@lru_cache(maxsize=1)
def load_categories() -> dict[str, list[str]]:
    """카테고리별 재료 목록(data/ingredient_categories.json)."""
    return _load_json("ingredient_categories.json")


@lru_cache(maxsize=1)
def known_ingredients() -> tuple[str, ...]:
    """앱이 아는 모든 재료 이름(가나다순)."""
    return tuple(sorted({i for items in load_categories().values() for i in items}))


_TAG_RE = re.compile(r"<[^>]*>")
_HANGUL_RE = re.compile(r"[가-힣]")


def _clean(token: str) -> str:
    """HTML 태그와 특수문자를 지우고 한글/영문/숫자/공백만 남긴 뒤 길이를 제한한다."""
    token = _TAG_RE.sub(" ", token or "")
    token = re.sub(r"[^0-9A-Za-z가-힣 ]", "", token)
    return re.sub(r"\s+", " ", token).strip()[:MAX_TOKEN_LEN]


def normalize(name: str) -> str:
    """재료 이름 하나를 정규화한다.

    순서: 동의어 사전(영문은 대소문자 무시) → 정확히 일치하는 재료 → 부분 일치 → 입력 그대로.
    부분 일치는 '청양고추'→'고추', '방울토마토'→'토마토'처럼 **재료명으로 끝나는 경우**만 허용한다
    ('계란말이'→'계란'처럼 요리 이름을 재료로 오인하지 않기 위해).
    한글이 없고 사전에도 없는 토큰(알 수 없는 영문/숫자)은 버린다(빈 문자열).
    """
    name = _clean(name)
    if not name:
        return ""
    synonyms, known = load_synonyms(), set(known_ingredients())
    for cand in (name, name.replace(" ", "")):
        if cand.lower() in synonyms:
            return synonyms[cand.lower()]
        if cand in known:
            return cand
    name = name.replace(" ", "")
    if len(name) >= 2:
        # 입력이 재료명으로 끝나는 경우 (가장 긴 재료명 우선)
        suffix = [k for k in known if len(k) >= 2 and name.endswith(k)]
        if suffix:
            return max(suffix, key=len)
        # 입력이 어떤 재료명의 일부인 경우 (후보가 하나일 때만)
        containing = [k for k in known if name in k]
        if len(containing) == 1:
            return containing[0]
    if not _HANGUL_RE.search(name):
        return ""
    return name


def parse_ingredients(text: str) -> list[str]:
    """쉼표/줄바꿈 등으로 구분된 입력을 정규화된 재료 리스트로 바꾼다.

    빈 항목과 특수문자는 버리고 중복은 순서를 유지한 채 제거한다. 최대 MAX_ITEMS개.
    """
    result: list[str] = []
    for token in re.split(r"[,\n、/;]", text or ""):
        name = normalize(token)
        if name and name not in result:
            result.append(name)
        if len(result) >= MAX_ITEMS:
            break
    return result


def unknown_ingredients(names: list[str]) -> list[str]:
    """데이터에 없는(인식하지 못한) 재료만 골라 반환한다."""
    known = set(known_ingredients())
    return [n for n in names if n not in known]
