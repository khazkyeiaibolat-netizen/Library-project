"""Kazakh / English interface. Kazakh is the default (the coursework language).

Text lives in translations.py as  key -> (kazakh, english).
Data stored in the database (genres, return statuses) is kept in Kazakh, exactly as in the
coursework, and translated only for display here.
"""
import zlib
from datetime import date

from flask import session

from .translations import TEXT

LANGS = ("kk", "en")
DEFAULT_LANG = "kk"

GENRES_EN = {
    "Роман": "Novel", "Тарихи роман": "Historical novel", "Повесть": "Novella", "Әңгіме": "Short story",
    "Поэзия": "Poetry", "Драма": "Drama", "Фантастика": "Science fiction", "Детектив": "Detective",
    "Оқулық": "Textbook", "Ғылыми-көпшілік": "Popular science",
}
STATUS_EN = {"Қайтарылды": "Returned", "Кешігіп қайтарылды": "Returned late"}


def lang():
    value = session.get("lang", DEFAULT_LANG)
    return value if value in LANGS else DEFAULT_LANG


def t(key, **params):
    entry = TEXT.get(key)
    if entry is None:
        return key                                   # visible in the UI and caught by the test-suite
    text = entry[LANGS.index(lang())]
    return text.format(**params) if params else text


def genre_label(genre):
    if not genre:
        return "—"
    return GENRES_EN.get(genre, genre) if lang() == "en" else genre


def status_label(status):
    return STATUS_EN.get(status, status) if lang() == "en" else status


def fmt_date(iso):
    if not iso:
        return "—"
    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso)
    return d.strftime("%d.%m.%Y")


def days_until(iso):
    """Whole days from today to the given ISO date (negative = already passed)."""
    return (date.fromisoformat(iso) - date.today()).days


def cover_class(book_or_genre):
    """Stable colour class for book covers, chosen from the genre."""
    genre = book_or_genre if isinstance(book_or_genre, str) or book_or_genre is None else book_or_genre["genre"]
    return "cv%d" % (zlib.crc32((genre or "").encode("utf-8")) % 8)


def init_app(app):
    app.jinja_env.globals.update(
        t=t, lang=lang, genre_label=genre_label, status_label=status_label, fmt_date=fmt_date,
        days_until=days_until, cover_class=cover_class, today=lambda: date.today().isoformat(),
        LANGS=LANGS)
