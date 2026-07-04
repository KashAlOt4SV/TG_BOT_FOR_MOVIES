from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import aiohttp
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

KINOPOISK_SEARCH_URL = "https://kinopoiskapiunofficial.tech/api/v2.1/films/search-by-keyword"
KINOPOISK_FILM_URL = "https://kinopoiskapiunofficial.tech/api/v2.2/films/{film_id}"
OMDB_URL = "https://www.omdbapi.com/"

MATCH_THRESHOLD = 58

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


@dataclass
class MovieLookupResult:
    found: bool
    query: str
    matched_title: str | None = None
    year: str | None = None
    description: str | None = None
    kinopoisk_rating: str | None = None
    imdb_rating: str | None = None
    type_label: str | None = None
    not_configured: bool = False


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s:.-]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _translit(text: str) -> str:
    result = []
    for char in text.lower():
        result.append(TRANSLIT.get(char, char))
    return "".join(result)


def _search_variants(title: str) -> list[str]:
    variants: list[str] = []
    raw = title.strip()
    normalized = _normalize(raw)

    for candidate in (raw, normalized, normalized.replace(" ", "")):
        if candidate and candidate not in variants:
            variants.append(candidate)

    if " " in normalized and ":" not in normalized:
        parts = normalized.split()
        if len(parts) == 2 and len(parts[0]) <= 4:
            colon = f"{parts[0]}:{parts[1]}"
            if colon not in variants:
                variants.append(colon)
            merged = parts[0] + parts[1]
            if merged not in variants:
                variants.append(merged)

    translit = _translit(normalized)
    if translit and translit not in variants:
        variants.append(translit)
    if translit and " " in translit and ":" not in translit:
        tparts = translit.split()
        if len(tparts) == 2 and len(tparts[0]) <= 4:
            tcolon = f"{tparts[0]}:{tparts[1]}"
            if tcolon not in variants:
                variants.append(tcolon)

    return variants


def _film_titles(film: dict) -> list[str]:
    titles = []
    for key in ("nameRu", "nameEn", "nameOriginal"):
        value = film.get(key)
        if value and value not in titles:
            titles.append(str(value))
    return titles


def _best_match_score(query: str, film: dict) -> int:
    titles = _film_titles(film)
    if not titles:
        return 0
    normalized_query = _normalize(query)
    scores = []
    for title in titles:
        scores.append(fuzz.token_set_ratio(normalized_query, _normalize(title)))
        scores.append(fuzz.partial_ratio(normalized_query, _normalize(title)))
    return max(scores)


def _type_label(raw: str | None) -> str | None:
    mapping = {
        "FILM": "Фильм",
        "TV_SERIES": "Сериал",
        "MINI_SERIES": "Мини-сериал",
        "TV_SHOW": "ТВ-шоу",
        "ANIME": "Аниме",
        "ANIME_SERIES": "Аниме-сериал",
    }
    return mapping.get(raw or "", raw)


class MovieLookupService:
    def __init__(
        self,
        kinopoisk_api_key: str | None,
        omdb_api_key: str | None,
    ):
        self.kinopoisk_api_key = kinopoisk_api_key
        self.omdb_api_key = omdb_api_key

    async def lookup(self, title: str) -> MovieLookupResult:
        if not self.kinopoisk_api_key:
            return MovieLookupResult(
                found=False,
                query=title,
                not_configured=True,
            )

        try:
            return await self._lookup_with_kinopoisk(title)
        except Exception:
            logger.exception("Movie lookup failed for %r", title)
            return MovieLookupResult(found=False, query=title)

    async def _lookup_with_kinopoisk(self, title: str) -> MovieLookupResult:
        candidates: dict[int, dict] = {}

        async with aiohttp.ClientSession() as session:
            for variant in _search_variants(title):
                films = await self._search_kinopoisk(session, variant)
                for film in films:
                    film_id = film.get("filmId") or film.get("kinopoiskId")
                    if film_id:
                        candidates[int(film_id)] = film

            if not candidates:
                return MovieLookupResult(found=False, query=title)

            best_id = max(
                candidates,
                key=lambda fid: _best_match_score(title, candidates[fid]),
            )
            best_film = candidates[best_id]
            score = _best_match_score(title, best_film)

            if score < MATCH_THRESHOLD:
                return MovieLookupResult(found=False, query=title)

            details = await self._fetch_kinopoisk_details(session, best_id)
            if not details:
                return MovieLookupResult(found=False, query=title)

            matched_title = (
                details.get("nameRu")
                or details.get("nameEn")
                or details.get("nameOriginal")
                or best_film.get("nameRu")
                or title
            )

            kp_rating = details.get("ratingKinopoisk")
            if kp_rating is None:
                kp_rating = best_film.get("rating")
            kp_rating_str = f"{kp_rating:.1f}" if isinstance(kp_rating, (int, float)) else (
                str(kp_rating) if kp_rating else None
            )

            imdb_rating = None
            imdb_id = details.get("imdbId") or best_film.get("imdbId")
            if imdb_id and self.omdb_api_key:
                imdb_rating = await self._fetch_imdb_rating(session, imdb_id)

            description = details.get("description") or details.get("shortDescription")
            if description and len(description) > 900:
                description = description[:897].rstrip() + "..."

            year = details.get("year")
            year_str = str(year) if year else None

            return MovieLookupResult(
                found=True,
                query=title,
                matched_title=str(matched_title),
                year=year_str,
                description=description,
                kinopoisk_rating=kp_rating_str,
                imdb_rating=imdb_rating,
                type_label=_type_label(details.get("type") or best_film.get("type")),
            )

    async def _search_kinopoisk(
        self,
        session: aiohttp.ClientSession,
        keyword: str,
    ) -> list[dict]:
        headers = {"X-API-KEY": self.kinopoisk_api_key}
        params = {"keyword": keyword}
        async with session.get(
            KINOPOISK_SEARCH_URL,
            headers=headers,
            params=params,
            timeout=aiohttp.ClientTimeout(total=12),
        ) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            return data.get("films") or data.get("items") or []

    async def _fetch_kinopoisk_details(
        self,
        session: aiohttp.ClientSession,
        film_id: int,
    ) -> dict | None:
        headers = {"X-API-KEY": self.kinopoisk_api_key}
        url = KINOPOISK_FILM_URL.format(film_id=film_id)
        async with session.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=12),
        ) as resp:
            if resp.status != 200:
                return None
            return await resp.json()

    async def _fetch_imdb_rating(
        self,
        session: aiohttp.ClientSession,
        imdb_id: str,
    ) -> str | None:
        if not imdb_id.startswith("tt"):
            imdb_id = f"tt{imdb_id}" if imdb_id.isdigit() else imdb_id

        params = {"i": imdb_id, "apikey": self.omdb_api_key}
        async with session.get(
            OMDB_URL,
            params=params,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            if data.get("Response") == "False":
                return None
            rating = data.get("imdbRating")
            return str(rating) if rating and rating != "N/A" else None


def format_lookup_message(result: MovieLookupResult, proposer_hint: str | None = None) -> str:
    if result.not_configured:
        return (
            "ℹ️ Поиск по Кинопоиску недоступен.\n"
            "Администратору бота нужно указать <code>KINOPOISK_API_KEY</code> в настройках."
        )

    if not result.found:
        lines = [
            f"😕 Не удалось найти «<b>{result.query}</b>».",
            "",
            "Попробуйте поискать в интернете или уточните точное название "
            "у того, кто предложил фильм.",
        ]
        if proposer_hint:
            lines.append(f"\nПредложил: {proposer_hint}")
        return "\n".join(lines)

    lines = [f"🎬 <b>{result.matched_title}</b>"]
    meta = []
    if result.type_label:
        meta.append(result.type_label)
    if result.year:
        meta.append(result.year)
    if meta:
        lines.append(f"<i>{', '.join(meta)}</i>")

    lines.append("")
    if result.description:
        lines.append("📝 <b>Описание:</b>")
        lines.append(result.description)
        lines.append("")

    ratings = []
    if result.kinopoisk_rating:
        ratings.append(f"⭐ Кинопоиск: <b>{result.kinopoisk_rating}</b>")
    if result.imdb_rating:
        ratings.append(f"🎬 IMDb: <b>{result.imdb_rating}</b>")
    elif result.kinopoisk_rating:
        ratings.append("🎬 IMDb: —")

    if ratings:
        lines.extend(ratings)

    if result.query.lower() != (result.matched_title or "").lower():
        lines.append("")
        lines.append(f"🔍 Запрос: «{result.query}»")

    return "\n".join(lines)
