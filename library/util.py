"""Small helpers shared by the views."""
import math
from urllib.parse import urlencode

from flask import request


def to_int(value, default=None, minimum=None, maximum=None):
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if minimum is not None and n < minimum:
        return default
    if maximum is not None and n > maximum:
        return default
    return n


def clean(value, max_len=200):
    """Trim whitespace and cap the length of free-text input."""
    return (value or "").strip()[:max_len]


class Page:
    """Pagination state for a list view."""

    def __init__(self, total, per_page):
        self.total = total
        self.per_page = per_page
        self.pages = max(1, math.ceil(total / per_page))
        self.page = min(max(to_int(request.args.get("page"), 1, 1) or 1, 1), self.pages)
        self.offset = (self.page - 1) * per_page

    def window(self, span=2):
        lo, hi = max(1, self.page - span), min(self.pages, self.page + span)
        return range(lo, hi + 1)


def args_without(*names, **extra):
    """Current query-string arguments minus some names (used to build pagination links)."""
    data = {k: v for k, v in request.args.items() if k not in names and v != ""}
    data.update(extra)
    return data


def page_url(n):
    """URL of the current list page with ?page=n (other filters are kept)."""
    args = request.args.to_dict()
    args["page"] = n
    return request.path + "?" + urlencode(args)
