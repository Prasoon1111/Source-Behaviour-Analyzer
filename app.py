"""Flask app for exploring aggregate news-source behaviour."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
import re
import string
from threading import Lock

import requests
from flask import Flask, jsonify, render_template, request
import tldextract

from config import MAX_ARTICLES
from news_source import fetch_articles, is_indian_domain

app = Flask(__name__)

AGE_BUCKETS = ["Under 30 days", "30 days to 1 year", "Over 1 year", "Unknown"]
REGISTRATION_CACHE = {}
REGISTRATION_CACHE_LOCK = Lock()
DOMAIN_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=())


def demo_articles():
    """Return six sample articles with copied text and clustered timestamps."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    shared_snippet = (
        "The athlete delivered a remarkable performance in the final, "
        "earning a silver medal for the country."
    )
    samples = [
        ("Athlete wins silver in final", shared_snippet),
        ("Silver medal secured after close contest", shared_snippet),
        ("A memorable result for the national team", shared_snippet),
        ("Final brings a silver medal finish", shared_snippet),
        ("Fans celebrate the result", "Supporters gathered to celebrate the result after the event."),
        ("Competition concludes with strong performances", "The competition ended after a series of close matches."),
    ]
    domains = [
        "daily-sample.example",
        "city-report.example",
        "morning-wire.example",
        "sports-desk.example",
        "public-journal.example",
        "evening-brief.example",
    ]

    return [
        {
            "title": title,
            "snippet": snippet,
            "url": f"https://{domain}/demo-article-{index + 1}",
            "published_at": (now - timedelta(minutes=index * 9)).isoformat().replace("+00:00", "Z"),
            "source_domain": domain,
        }
        for index, ((title, snippet), domain) in enumerate(zip(samples, domains))
    ]


def parse_published_at(value):
    """Parse an ISO timestamp and return it in UTC."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (AttributeError, ValueError):
        return None


def data_delay_message(raw_response):
    """Return GNews's optional real-time article delay message."""
    information = (raw_response or {}).get("information")
    if not isinstance(information, dict):
        return None
    real_time_articles = information.get("realTimeArticles")
    if not isinstance(real_time_articles, dict):
        return None
    return real_time_articles.get("message")


def registrable_domain(domain):
    """Remove www and return the registered domain portion."""
    domain = domain.lower().removeprefix("www.").rstrip(".")
    extracted = DOMAIN_EXTRACTOR(domain)
    return extracted.top_domain_under_public_suffix or domain


def registration_lookup(domain):
    """Return a registration date or a specific reason it is unavailable."""
    try:
        response = requests.get(
            f"https://rdap.org/domain/{domain}",
            headers={"User-Agent": "BehaviourCoordinationIndicators/1.0"},
            timeout=5,
            allow_redirects=True,
        )
        response.raise_for_status()
        events = response.json().get("events", [])
        for event in events:
            if event.get("eventAction", "").lower() in {"registration", "registered"}:
                registered = parse_published_at(event.get("eventDate", ""))
                if registered:
                    return {"registered_at": registered.isoformat(), "reason": None}
        return {"registered_at": None, "reason": "registration date hidden"}
    except requests.Timeout:
        return {"registered_at": None, "reason": "timeout"}
    except (requests.RequestException, ValueError, AttributeError):
        return {"registered_at": None, "reason": "lookup failed"}


def cached_registration_lookup(domain):
    """Read or populate the in-memory registration cache."""
    with REGISTRATION_CACHE_LOCK:
        cached = REGISTRATION_CACHE.get(domain)
    if cached is not None:
        return cached

    result = registration_lookup(domain)
    with REGISTRATION_CACHE_LOCK:
        REGISTRATION_CACHE[domain] = result
    return result


def source_age_counts(articles):
    """Group source domains by registration age and retain lookup evidence."""
    counts = Counter({bucket: 0 for bucket in AGE_BUCKETS})
    now = datetime.now(timezone.utc)
    domain_map = {
        domain: registrable_domain(domain)
        for domain in {article["source_domain"] for article in articles}
    }
    registrable_domains = set(domain_map.values())
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(registrable_domains)))) as executor:
        lookups = dict(zip(registrable_domains, executor.map(cached_registration_lookup, registrable_domains)))

    details = []
    for domain, rdap_domain in sorted(domain_map.items()):
        lookup = lookups[rdap_domain]
        registered = parse_published_at(lookup["registered_at"]) if lookup["registered_at"] else None
        age_days = (now - registered).days if registered else None

        if age_days is None or age_days < 0:
            bucket = "Unknown"
        elif age_days < 30:
            bucket = "Under 30 days"
        elif age_days <= 365:
            bucket = "30 days to 1 year"
        else:
            bucket = "Over 1 year"
        counts[bucket] += 1
        details.append({
            "domain": domain,
            "rdap_domain": rdap_domain,
            "bucket": bucket,
            "registration_date": registered.date().isoformat() if registered else None,
            "unknown_reason": lookup["reason"],
        })

    return dict(counts), details


def normalized_snippet(snippet):
    """Lowercase snippets and remove punctuation and repeated spaces."""
    without_punctuation = snippet.translate(str.maketrans("", "", string.punctuation))
    return re.sub(r"\s+", " ", without_punctuation.lower()).strip()


def busiest_two_hour_window(articles):
    """Return article count, article numbers, and endpoints for the busiest window."""
    published = sorted(
        (timestamp, article["number"])
        for article in articles
        if (timestamp := parse_published_at(article["published_at"])) is not None
    )
    start = best_start = best_end = 0
    for end, (timestamp, _) in enumerate(published):
        while timestamp - published[start][0] > timedelta(hours=2):
            start += 1
        if end - start + 1 > best_end - best_start:
            best_start, best_end = start, end + 1
    window = published[best_start:best_end]
    return {
        "count": len(window),
        "article_numbers": sorted(number for _, number in window),
        "start": window[0][0].isoformat() if window else None,
        "end": window[-1][0].isoformat() if window else None,
    }


def analyse_articles(articles, is_demo=False, search_details=None, raw_response=None):
    """Build aggregate indicators and neutral summary text."""
    articles = [
        {
            **article,
            "number": index,
            "source_domain": article["source_domain"].lower().removeprefix("www.").rstrip("."),
            "source_name": article.get("source_name") or article["source_domain"],
            "origin": article.get("origin") or (
                "India"
                if str(article.get("source_country", "")).lower() == "in" or is_indian_domain(article["source_domain"])
                else "International"
            ),
            "published_at_ist": (
                (parse_published_at(article["published_at"]) + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M IST")
                if parse_published_at(article["published_at"])
                else "Unknown"
            ),
        }
        for index, article in enumerate(articles, start=1)
    ]
    total = len(articles)
    source_domains = sorted({article["source_domain"] for article in articles})
    source_total = len(source_domains)
    age_counts, age_details = source_age_counts(articles)
    hours = Counter()
    snippets = [normalized_snippet(article["snippet"]) for article in articles]
    parents = list(range(total))

    def find_group(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for left in range(total):
        if not snippets[left]:
            continue
        for right in range(left + 1, total):
            if not snippets[right]:
                continue
            similar = (
                snippets[left] in snippets[right]
                or snippets[right] in snippets[left]
                or SequenceMatcher(None, snippets[left], snippets[right]).ratio() >= 0.8
            )
            if similar:
                left_group = find_group(left)
                right_group = find_group(right)
                parents[right_group] = left_group

    snippet_clusters = {}
    for index, text in enumerate(snippets):
        if text:
            snippet_clusters.setdefault(find_group(index), []).append(articles[index])
    matching_groups = [
        [article["number"] for article in group]
        for group in snippet_clusters.values()
        if len(group) > 1
    ]
    matching_numbers = sorted({number for group in matching_groups for number in group})
    matching_sources = {
        article["source_domain"]
        for group in snippet_clusters.values()
        if len(group) > 1
        for article in group
    }
    hour_articles = {}
    for article in articles:
        published = parse_published_at(article["published_at"])
        if published:
            ist = published + timedelta(hours=5, minutes=30)
            hours[str(ist.hour)] += 1
            hour_articles.setdefault(str(ist.hour), []).append(article["number"])

    burst = busiest_two_hour_window(articles)
    timestamps = [parse_published_at(article["published_at"]) for article in articles]
    timestamps = [timestamp for timestamp in timestamps if timestamp]
    time_span_hours = (max(timestamps) - min(timestamps)).total_seconds() / 3600 if len(timestamps) > 1 else 0
    newest_age_hours = max(0, (datetime.now(timezone.utc) - max(timestamps)).total_seconds() / 3600) if timestamps else None
    count_summary = f"{total} articles from {source_total} sources"

    if total < 3:
        sentence = f"Too few sources to say anything about the pattern in these {count_summary}."
    elif total and burst["count"] / total >= 0.7 and time_span_hours >= 6:
        sentence = f"These {count_summary} share an unusually narrow posting window."
    else:
        sentence = f"No unusual pattern was found in these {count_summary}."

    india_count = len({article["source_domain"] for article in articles if article["origin"] == "India"})
    searched_at = (search_details or {}).get("searched_at") or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    details = search_details or {
        "query": "Demo data",
        "provider": "Built-in demo",
        "parameters": {"country": "in", "lang": "en", "from": "Demo timestamps", "max": MAX_ARTICLES, "sortby": "relevance"},
        "searched_at": searched_at,
    }

    return {
        "articles": articles,
        "is_demo": is_demo,
        "neutral_sentence": sentence,
        "source_domains": source_domains,
        "source_total": source_total,
        "count_summary": count_summary,
        "newest_age_hours": round(newest_age_hours, 1) if newest_age_hours is not None else None,
        "india_count": india_count,
        "india_note": f"Only {india_count} Indian sources found for this search." if india_count < MAX_ARTICLES else None,
        "total": total,
        "search_details": details,
        "raw_response": raw_response or {},
        "window_note": (search_details or {}).get("window_note"),
        "data_delay_note": data_delay_message(raw_response),
        "indicators": {
            "source_age": {"counts": age_counts, "details": age_details},
            "posting_hours_ist": dict(sorted(hours.items(), key=lambda item: int(item[0]))),
            "identical_text": {"count": len(matching_sources), "total": source_total},
            "burst_profile": {"count": burst["count"], "total": total, "time_span_hours": round(time_span_hours, 1)},
        },
        "calculations": {
            "source_age": age_details,
            "posting_hours_ist": hour_articles,
            "identical_text": {"groups": matching_groups, "article_numbers": matching_numbers},
            "burst_profile": burst,
        },
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/analyse")
def analyse():
    query = (request.get_json(silent=True, force=True) or {}).get("query", "").strip()
    if not query:
        return jsonify({"message": "No articles found. Try a different search."}), 400

    try:
        result = fetch_articles(query)
    except (requests.RequestException, ValueError):
        result = {"articles": [], "search_details": None, "raw_response": {}}

    if not result["articles"]:
        return jsonify({"message": "No articles found. Try 2-3 short keywords. The free news plan may also delay articles by up to 12 hours."}), 404
    result["search_details"]["window_note"] = result.get("window_note")
    result["search_details"]["window_used"] = result["search_details"].get("window_used")
    response = analyse_articles(result["articles"], search_details=result["search_details"], raw_response=result["raw_response"])
    response["data_delay_note"] = result.get("data_delay_note")
    return jsonify(response)


@app.get("/api/demo")
def demo():
    return jsonify(analyse_articles(demo_articles(), is_demo=True))


if __name__ == "__main__":
    app.run(debug=True)