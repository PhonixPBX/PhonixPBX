from phonix.services import listing as ls


def test_matches_casefold_and_umlauts():
    assert ls.matches("mül", ["Anna Müller"]) and ls.matches("MEI", ["meier"])
    assert ls.matches("", ["x"]) and ls.matches("  ", [None])
    assert not ls.matches("x", [None, ""])


def test_search_literal_characters():
    items = ["a.b", "axb", "50%", "(x)", "<b>"]
    assert ls.search(items, ".", lambda s: [s]) == ["a.b"]
    assert ls.search(items, "%", lambda s: [s]) == ["50%"]
    assert ls.search(items, "(", lambda s: [s]) == ["(x)"]


def test_search_keeps_order():
    assert ls.search(["b1", "a1", "c2"], "1", lambda s: [s]) == ["b1", "a1"]


def test_parse_page_and_per_page():
    assert [ls.parse_page(v) for v in ("3", "0", "-2", "x", None)] == [3, 1, 1, 1, 1]
    assert ls.parse_per_page("100") == 100 and ls.parse_per_page("all") is None
    assert ls.parse_per_page("7") == 50 and ls.parse_per_page(None) == 50
    assert ls.parse_per_page("all", ls.PER_PAGE_NO_ALL) == 50


def test_page_of_clamps():
    items = list(range(120))
    p = ls.page_of(items, 500, "", 99, 50)
    assert (p.page, p.pages, p.start, p.end, p.items[0]) == (3, 3, 101, 120, 100)
    assert ls.page_of(items, 500, "", 0, 50).page == 1
    empty = ls.page_of([], 500, "zz", 1, 50)
    assert (empty.pages, empty.start, empty.end, empty.matched) == (1, 0, 0, 0)
    assert ls.page_of(items, 120, "", 1, None).items == items


def test_page_links():
    p = ls.page_of(list(range(500)), 500, "", 6, 50)
    assert p.page_links() == [1, None, 4, 5, 6, 7, 8, 9, 10]
    assert ls.page_of(list(range(100)), 100, "", 1, 50).page_links() == [1, 2]


def test_query():
    p = ls.page_of(list(range(500)), 500, "mei er", 2, 50)
    assert p.query() == "q=mei+er&page=2"
    assert p.query(page=3) == "q=mei+er&page=3"
    assert p.query(q="") == ""
    assert p.query(per_page=None) == "q=mei+er&per_page=all"


def test_slice_api():
    assert ls.slice_api(list(range(10)), 8, None) == [8, 9]
    assert ls.slice_api(list(range(10)), 2, 3) == [2, 3, 4]


def test_sqlite_casefold(session):
    from sqlalchemy import func, select

    assert session.scalar(select(func.casefold("ÄBC"))) == "äbc"


def test_highlight_escapes():
    from phonix.web.templating import templates

    hl = templates.env.filters["highlight"]
    assert str(hl("<b>Meier</b>", "mei")) == "&lt;b&gt;<mark>Mei</mark>er&lt;/b&gt;"
    assert str(hl("a.b axb", ".")) == "a<mark>.</mark>b axb"
    assert str(hl("x", "")) == "x"
