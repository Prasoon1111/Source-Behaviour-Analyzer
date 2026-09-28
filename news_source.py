"""Fetch and normalize articles from GNews."""

import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from config import INDIAN_DOMAINS, MAX_ARTICLES

load_dotenv()

GNEWS_SEARCH_URL = "https://gnews.io/api/v4/search"


def is_indian_domain(domain):
    """Recognize configured Indian publishers and all .in domains."""
    domain = domain.lower().removeprefix("www.").rstrip(".")
    return domain.endswith(".in") or any(
        domain == known or domain.endswith(f".{known}") for known in INDIAN_DOMAINS
    )


def clean_search_query(query):
    """Remove common filler words before sending a query to GNews."""
    query = re.sub(r"\b(?:and|the|of|to|in)\b", " ", query, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", query).strip()


def fetch_articles(query):
    """Retry wider date windows and prioritize articles from Indian sources."""
    api_key = os.getenv("GNEWS_API_KEY")
    now = datetime.now(timezone.utc)
    cleaned_query = clean_search_query(query)
    details = {
        "query": query,
        "search_query": cleaned_query,
        "provider": "GNews",
        "parameters": {
            "q": cleaned_query,
            "country": "in",
            "lang": "en",
            "max": 10,
            "sortby": "relevance",
            "apikey": "[hidden]",
        },
        "searched_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "article_limit": MAX_ARTICLES,
    }
    if not api_key or not cleaned_query:
        return {
            "articles": [],
            "search_details": details,
            "raw_response": {},
            "window_note": None,
            "data_delay_note": None,
        }

    windows = [("last 24 hours", timedelta(hours=24)), ("last 7 days", timedelta(days=7)), ("last 30 days", timedelta(days=30))]
    raw_response = {}
    normalized = []
    window_note = None
    used_window = None

    for index, (window_label, duration) in enumerate(windows):
        time_from = (now - duration).isoformat(timespec="seconds").replace("+00:00", "Z")
        parameters = {
            "q": cleaned_query,
            "country": "in",
            "lang": "en",
            "from": time_from,
            "max": 10,
            "sortby": "relevance",
        }
        response = requests.get(
            GNEWS_SEARCH_URL,
            params={**parameters, "apikey": api_key},
            timeout=5,
        )
        response.raise_for_status()
        raw_response = response.json()
        normalized = []

        for article in raw_response.get("articles", []):
            source = article.get("source", {})
            source_url = source.get("url", "")
            domain = (urlparse(source_url).hostname or "").lower().removeprefix("www.")
            if not domain:
                domain = (urlparse(article.get("url", "")).hostname or "").lower().removeprefix("www.")
            published = article.get("publishedAt", "")
            try:
                published = datetime.fromisoformat(published.replace("Z", "+00:00"))
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                published = published.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            except (AttributeError, ValueError):
                published = ""

            if domain:
                source_country = str(source.get("country", "")).lower()
                origin = "India" if source_country == "in" or is_indian_domain(domain) else "International"
                normalized.append(
                    {
                        "title": article.get("title", ""),
                        "snippet": article.get("description", "") or "",
                        "url": article.get("url", ""),
                        "published_at": published,
                        "source_domain": domain,
                        "source_name": source.get("name", "") or domain,
                        "source_country": source_country,
                        "origin": origin,
                    }
                )

        if normalized:
            used_window = window_label
            if index:
                previous_label = windows[index - 1][0]
                window_note = f"No articles in the {previous_label}. Showing results from the {window_label}."
            else:
                window_note = f"Showing results from the {window_label}."
            details["parameters"] = {**parameters, "apikey": "[hidden]"}
            break

    normalized.sort(key=lambda item: item["origin"] != "India")
    selected = normalized[:MAX_ARTICLES]
    details["window_used"] = used_window
    information = raw_response.get("information", {})
    real_time_articles = information.get("realTimeArticles", {}) if isinstance(information, dict) else {}
    data_delay_note = real_time_articles.get("message") if isinstance(real_time_articles, dict) else None
    return {
        "articles": selected,
        "search_details": details,
        "raw_response": raw_response,
        "window_note": window_note,
        "data_delay_note": data_delay_note,
    }