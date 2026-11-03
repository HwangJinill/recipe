"""재료 기반 요리 추천 앱."""
from html import escape
from pathlib import Path

import streamlit as st

from recommender import CUISINES, DIFFICULTIES, load_recipes, recommend_with_fallback
from utils import known_ingredients, load_categories, parse_ingredients, unknown_ingredients

TIME_OPTIONS = {"상관없음": None, "15분 이내": 15, "30분 이내": 30, "60분 이내": 60}
DIFFICULTY_ICONS = {"쉬움": "★☆☆", "보통": "★★☆", "어려움": "★★★"}
PLACEHOLDER = "선택하세요"
EXAMPLES = [
    ("계란, 양파, 대파, 밥", ["계란", "양파", "대파", "밥"]),
    ("두부, 김치, 돼지고기", ["두부", "김치", "돼지고기"]),
    ("파스타면, 마늘, 베이컨", ["파스타면", "마늘", "베이컨"]),
    ("닭고기, 감자, 양파", ["닭고기", "감자", "양파"]),
]


@st.cache_data
def get_recipes() -> list[dict]:
    return load_recipes()


@st.cache_data
def get_css() -> str:
    return (Path(__file__).parent / "styles.css").read_text(encoding="utf-8")


# ---------- 상태 관리 ----------
def _cat_key(category: str) -> str:
    return f"cat_{category}"


def init_state() -> None:
    st.session_state.setdefault("typed", [])
    st.session_state.setdefault("searched", False)
    st.session_state.setdefault("ing_text", "")


def current_ingredients() -> list[str]:
    """직접 입력한 재료 + 카테고리에서 고른 재료(중복 제거, 순서 유지)."""
    result = list(st.session_state.typed)
    for category in load_categories():
        for name in st.session_state.get(_cat_key(category), []):
            if name not in result:
                result.append(name)
    return result


def add_typed() -> None:
    for name in parse_ingredients(st.session_state.ing_text):
        if name not in st.session_state.typed:
            st.session_state.typed.append(name)
    st.session_state.ing_text = ""


def remove_ingredient(name: str) -> None:
    if name in st.session_state.typed:
        st.session_state.typed.remove(name)
    for category in load_categories():
        key = _cat_key(category)
        if name in st.session_state.get(key, []):
            st.session_state[key] = [n for n in st.session_state[key] if n != name]


def clear_ingredients() -> None:
    st.session_state.typed = []
    for category in load_categories():
        st.session_state[_cat_key(category)] = []


def use_example(names: list[str]) -> None:
    """예시 재료로 입력을 대체하고 바로 추천을 실행한다."""
    clear_ingredients()
    st.session_state.typed = list(names)
    st.session_state.searched = True


def start_search() -> None:
    st.session_state.searched = True


# ---------- HTML 조각 ----------
def rate_class(rate: float) -> str:
    return "rate-high" if rate >= 0.8 else "rate-mid" if rate >= 0.5 else "rate-low"


def chip(text: str, kind: str) -> str:
    return f'<span class="chip chip-{kind}">{escape(text)}</span>'


def card_html(r: dict) -> str:
    """카드 상단: 요리명, 국가 배지, 시간/난이도, 일치율 막대, 필수 재료 칩."""
    rec, rate = r["recipe"], r["match_rate"]
    chips = "".join(
        chip(f"✓ {n}" + (" (양념)" if n in r["assumed"] else ""), "have") for n in r["have"]
    ) + "".join(chip(f"✕ {n}", "miss") for n in r["missing"])
    return (
        '<span class="rc-marker"></span>'
        f'<div class="rc-head"><span class="rc-name">{escape(rec["name"])}</span>'
        f'<span class="rc-badge c-{escape(rec["cuisine"])}">{escape(rec["cuisine"])}</span></div>'
        f'<div class="rc-meta">⏱ {rec["time_min"]}분 · 난이도 {DIFFICULTY_ICONS[rec["difficulty"]]} {escape(rec["difficulty"])}</div>'
        f'<div class="rc-rate"><span>일치율</span><span>{rate:.0%}</span></div>'
        f'<div class="rc-bar"><div class="rc-bar-fill {rate_class(rate)}" style="width:{rate * 100:.0f}%"></div></div>'
        f'<div>{chips}</div>'
    )


def ingredients_html(r: dict) -> str:
    parts = []
    for ing in r["ingredients"]:
        label = f"{ing['name']} {ing['amount']}"
        if ing["owned"]:
            parts.append(chip(f"✓ {label}" + (" (기본 양념)" if ing["assumed"] else ""), "have"))
        elif ing["required"]:
            parts.append(chip(f"✕ {label}", "miss"))
        else:
            parts.append(chip(f"{label} (선택)", "opt"))
    return "".join(parts)


# ---------- 화면 조각 ----------
def render_hero() -> None:
    st.markdown(
        '<div class="hero"><div class="hero-title">🍳 오늘 뭐 먹지?</div>'
        '<div class="hero-sub">냉장고 속 재료를 알려 주세요. 만들 수 있는 한식·일식·중식·양식을 골라 드려요.</div></div>',
        unsafe_allow_html=True,
    )


def render_inputs() -> None:
    """재료 입력(메인 영역). 모바일에서 사이드바가 접혀 있어도 바로 쓸 수 있다."""
    st.text_input("보유 재료", key="ing_text", on_change=add_typed,
                  placeholder="예: 계란, 양파, 대파  (쉼표로 구분하고 Enter)",
                  help="쉼표(,)로 여러 개를 구분하고 Enter를 누르면 추가돼요. 달걀→계란, 파→대파처럼 비슷한 이름은 자동으로 맞춰 드려요.")
    with st.expander("자주 쓰는 재료에서 고르기"):
        for category, items in load_categories().items():
            st.multiselect(category, items, key=_cat_key(category), placeholder=PLACEHOLDER)


def render_sidebar() -> dict:
    """사이드바에는 '조건'만 둔다. 설정 값을 dict로 반환한다."""
    with st.sidebar:
        st.subheader("요리 조건")
        st.caption("재료 입력과 추천 버튼은 화면 가운데에 있어요.")
        cuisines = st.multiselect("요리 종류", CUISINES, default=CUISINES, placeholder=PLACEHOLDER,
                                  help="먹고 싶은 종류만 남기고 나머지는 지워 보세요.")
        time_label = st.selectbox("조리 시간", list(TIME_OPTIONS))
        difficulties = st.multiselect("난이도", DIFFICULTIES, default=DIFFICULTIES, placeholder=PLACEHOLDER)

        st.divider()
        st.subheader("제외 · 옵션")
        exclude = st.multiselect("제외 재료 (알레르기/비선호)", list(known_ingredients()),
                                 placeholder=PLACEHOLDER,
                                 help="선택한 재료가 들어간 요리는 결과에서 빠져요.")
        staples_owned = st.checkbox("기본 양념(소금, 간장 등)은 있다고 가정", value=True)
        with st.expander("결과 개수 · 일치율 설정"):
            top_n = st.slider("최대 표시 개수", 1, 30, 10)
            min_rate = st.slider("최소 일치율 (%)", 0, 100, 40, step=5,
                                 help="이 값보다 일치율이 낮은 요리는 숨겨요.")

    return {
        "filters": {
            "cuisines": cuisines,
            "max_time": TIME_OPTIONS[time_label],
            "difficulties": difficulties,
            "exclude": exclude,
            "staples_owned": staples_owned,
            "min_rate": min_rate / 100,
        },
        "top_n": top_n,
    }


def render_tags(ings: list[str]) -> None:
    """입력한 재료를 태그 칩(버튼)으로 보여 준다. 누르면 삭제된다."""
    if not ings:
        return
    st.markdown("**내가 가진 재료** · 누르면 삭제돼요")
    with st.container(key="tags"):
        for name in ings:
            st.button(f"{name} ✕", key=f"rm_{name}", on_click=remove_ingredient, args=(name,))
    st.button("모두 지우기", on_click=clear_ingredients)
    unknown = unknown_ingredients(ings)
    if unknown:
        st.caption(f"인식하지 못한 재료: {', '.join(unknown)} (입력한 그대로 사용돼요)")


def render_examples() -> None:
    """예시 재료 버튼. 누르면 바로 추천이 실행된다."""
    for col, (label, names) in zip(st.columns(len(EXAMPLES)), EXAMPLES):
        col.button(label, key=f"ex_{label}", on_click=use_example, args=(names,), use_container_width=True)


def render_welcome() -> None:
    """첫 화면: 사용법 안내와 예시 재료 버튼."""
    st.markdown(
        '<div class="empty-box"><div class="empty-title">어떤 재료가 있나요?</div>'
        '<div class="empty-sub">위 입력창에 재료를 쓰고 <b>요리 추천받기</b>를 누르거나, '
        '아래 예시를 눌러 바로 시작해 보세요.</div></div>',
        unsafe_allow_html=True,
    )
    render_examples()


def render_empty(message: str, hint: str) -> None:
    st.markdown(
        f'<div class="empty-box"><div class="empty-title">{escape(message)}</div>'
        f'<div class="empty-sub">{escape(hint)}</div></div>',
        unsafe_allow_html=True,
    )


def render_card(r: dict) -> None:
    with st.container(border=True):
        st.markdown(card_html(r), unsafe_allow_html=True)
        with st.expander("재료 · 조리 순서 보기"):
            st.markdown("**재료**")
            st.markdown(ingredients_html(r), unsafe_allow_html=True)
            st.markdown("**조리 순서**")
            st.markdown("\n".join(f"{n}. {step}" for n, step in enumerate(r["recipe"]["steps"], 1)))


def render_grid(items: list[dict], per_row: int = 3) -> None:
    for start in range(0, len(items), per_row):
        row = items[start:start + per_row]
        for col, r in zip(st.columns(per_row), row):
            with col:
                render_card(r)


def render_results(ings: list[str], settings: dict) -> None:
    if not ings:
        render_empty("재료를 먼저 알려 주세요", "재료를 한 개 이상 입력하거나 선택해야 추천할 수 있어요. 아래 예시로 시작해 볼 수도 있어요.")
        render_examples()
        return
    filters = settings["filters"]
    if not filters["cuisines"] or not filters["difficulties"]:
        render_empty("조건을 확인해 주세요", "요리 종류와 난이도를 각각 한 개 이상 선택해 주세요. (조건은 사이드바에서 바꿀 수 있어요)")
        return

    overlap = [n for n in ings if n in filters["exclude"]]
    if overlap:
        st.warning(f"제외 재료에도 들어 있는 재료: {', '.join(overlap)}. 이 재료가 들어간 요리는 결과에서 빠져요.")

    top_n = settings["top_n"]
    results, is_fallback = recommend_with_fallback(ings, filters, 10**6, recipes=get_recipes())
    if not results:
        render_empty("딱 맞는 요리를 찾지 못했어요",
                     "재료를 더 추가하거나, 요리 종류·조리 시간·제외 재료 조건을 완화해 보세요.")
        return

    # 탭마다 상위 N개를 따로 뽑는다(전체 상위 N개로 자른 뒤 나누면 분류 탭이 비어 보인다).
    labels = ["전체"] + CUISINES
    groups = {"전체": results[:top_n]}
    for cuisine in CUISINES:
        groups[cuisine] = [r for r in results if r["recipe"]["cuisine"] == cuisine][:top_n]

    if is_fallback:
        st.warning("최소 일치율을 넘는 요리가 없어요. 재료를 더 추가해 보세요! 가장 근접한 요리를 보여 드려요.")
    else:
        st.markdown(f"#### 조건에 맞는 요리 {len(results)}개")
        st.caption(f"일치율이 높은 순으로 보여 드려요. 각 탭마다 최대 {top_n}개까지 표시해요.")

    for tab, label in zip(st.tabs([f"{label} ({len(groups[label])})" for label in labels]), labels):
        with tab:
            if groups[label]:
                render_grid(groups[label])
            else:
                st.caption("이 분류에는 추천 결과가 없어요.")


def main() -> None:
    st.set_page_config(page_title="오늘 뭐 먹지?", page_icon="🍳", layout="wide")
    st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
    init_state()

    settings = render_sidebar()
    render_hero()
    render_inputs()
    ings = current_ingredients()
    render_tags(ings)
    st.button("🍽️ 요리 추천받기", type="primary", on_click=start_search)
    st.caption("요리 종류·시간·제외 재료 같은 조건은 사이드바에서 바꿀 수 있어요. (모바일은 왼쪽 위 » 아이콘)")

    if st.session_state.searched:
        render_results(ings, settings)
    elif ings:
        render_empty("재료를 입력했어요!", "위의 '요리 추천받기' 버튼을 눌러 결과를 확인하세요.")
    else:
        render_welcome()


main()
