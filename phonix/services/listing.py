"""Search and paging helpers shared by the list views, the REST API and MCP."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar
from urllib.parse import urlencode

T = TypeVar("T")

PER_PAGE_DEFAULT = 50
# None means "all"
PER_PAGE_CHOICES: tuple[int | None, ...] = (25, 50, 100, None)
PER_PAGE_NO_ALL: tuple[int | None, ...] = (25, 50, 100)


def matches(q: str, values: Iterable[object]) -> bool:
    """Case-insensitive substring match of `q` in any non-None value; an empty `q` matches all."""
    needle = q.strip().casefold()
    if not needle:
        return True
    return any(needle in str(v).casefold() for v in values if v is not None)


def search(items: Iterable[T], q: str, fields: Callable[[T], Iterable[object]]) -> list[T]:
    """Keep the items for which `fields(item)` matches `q`, in input order."""
    return [item for item in items if matches(q, fields(item))]


def parse_page(value: object) -> int:
    try:
        page = int(str(value))
    except ValueError:
        return 1
    return page if page > 0 else 1


def parse_per_page(value: object, choices: tuple[int | None, ...] = PER_PAGE_CHOICES) -> int | None:
    if value == "all":
        return None if None in choices else PER_PAGE_DEFAULT
    try:
        number = int(str(value))
    except ValueError:
        return PER_PAGE_DEFAULT
    return number if number in choices else PER_PAGE_DEFAULT


@dataclass(frozen=True)
class ListPage(Generic[T]):
    items: list[T]  # the current page
    matched: int  # items matching the search
    total: int  # items without the search
    page: int
    per_page: int | None
    q: str
    choices: tuple[int | None, ...]

    @property
    def pages(self) -> int:
        if self.per_page is None:
            return 1
        return max(1, -(-self.matched // self.per_page))

    @property
    def start(self) -> int:
        """1-based number of the first item shown, 0 if nothing matched."""
        if self.matched == 0:
            return 0
        return 1 if self.per_page is None else (self.page - 1) * self.per_page + 1

    @property
    def end(self) -> int:
        return 0 if self.matched == 0 else self.start + len(self.items) - 1

    @property
    def searching(self) -> bool:
        return self.q != ""

    def page_links(self) -> list[int | None]:
        """Page numbers to link: first, last and the current page +-2; None marks a gap."""
        near = set(range(max(1, self.page - 2), min(self.pages, self.page + 2) + 1))
        wanted = sorted({1, self.pages} | near)
        links: list[int | None] = []
        previous = 0
        for number in wanted:
            if number - previous == 2:  # a gap of one page is shown as that page
                links.append(previous + 1)
            elif number - previous > 2:
                links.append(None)
            links.append(number)
            previous = number
        return links

    def query(self, **changes: object) -> str:
        """URL query for this page with `changes` applied, leaving out default values."""
        params: dict[str, object] = {"q": self.q, "page": self.page, "per_page": self.per_page}
        params.update(changes)
        if "page" not in changes and ("q" in changes or "per_page" in changes):
            params["page"] = 1
        out: list[tuple[str, str]] = []
        if params["q"]:
            out.append(("q", str(params["q"])))
        if params["page"] != 1:
            out.append(("page", str(params["page"])))
        if params["per_page"] != PER_PAGE_DEFAULT:
            out.append(("per_page", "all" if params["per_page"] is None else str(params["per_page"])))
        return urlencode(out)


def page_of(
    items: Sequence[T],
    total: int,
    q: str,
    page: int,
    per_page: int | None,
    choices: tuple[int | None, ...] = PER_PAGE_CHOICES,
) -> ListPage[T]:
    """Build a ListPage from the matching `items`, clamping `page` into range."""
    matched = len(items)
    pages = 1 if per_page is None else max(1, -(-matched // per_page))
    page = min(max(page, 1), pages)
    shown = list(items) if per_page is None else list(items[(page - 1) * per_page : page * per_page])
    return ListPage(shown, matched, total, page, per_page, q, choices)


def slice_api(items: Sequence[T], offset: int, limit: int | None) -> list[T]:
    return list(items[offset:] if limit is None else items[offset : offset + limit])
