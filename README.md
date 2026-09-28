# Source Behaviour Analyzer

*A clear, evidence-led look at how news articles are published and shared.*

## What is this?

Source Behaviour Analyzer is a small web app where you can search for a news topic and review a few recent articles together. It summarizes patterns in their sources, wording, and publication times. It does not decide whether a story is true.

## The problem it helps explore

When several outlets publish about the same story, their timing and wording can offer useful context. This app helps readers notice when articles appeared close together or use similar snippets, so they can choose what to examine further.

Those patterns do not prove coordination. The app never judges whether a claim is true or false, and it never labels an individual source as suspicious or unreliable.

## How it works

1. Enter a topic or a few keywords. The app removes the filler words “and,” “the,” “of,” “to,” and “in” before sending the search.
2. It asks GNews for English news from India, sorted by relevance. It starts with the last 24 hours, then retries with the last 7 days and last 30 days if needed.
3. GNews can return up to 10 candidate articles. The app puts Indian sources first and analyses up to 6 articles.
4. It calculates four summaries across those articles: source age, publishing hour in IST, near-identical snippets, and the busiest two-hour window.
5. It shows one neutral sentence based on the article count and the posting-time threshold.
6. It displays the articles and search details behind the numbers so readers can inspect the evidence themselves.

## The four indicators

### Source age

The app looks up each source’s registrable domain through RDAP and groups distinct domains by registration age. For example, a result might show 2 domains “Over 1 year” old and 1 “Unknown.”

An unavailable lookup includes its reason, such as “timeout,” “lookup failed,” or “registration date hidden.”

### Posting time-of-day

Each article’s publication hour is converted to India Standard Time (IST); the chart only shows hours with articles. For example, three articles published at 9:00 IST appear in that hour’s bar.

### Identical text

The app lowercases snippets, removes punctuation, and compares the remaining text. Two snippets are grouped when one contains the other or their text similarity is at least 0.8; the indicator counts distinct sources in matching groups.

For example, “The team won today!” and “the team won today” are treated as a match. News agencies like ANI and PTI supply the same text to many outlets, so shared text alone does not mean coordination.

### Burst profile

The app finds the largest number of articles that fit within any rolling two-hour window. For example, if 4 of 6 articles fit in one such window, it shows that count and the full time span from the oldest to newest article.

## How the final sentence is decided

The current code uses these rules, in order:

- **Fewer than 3 articles:** “Too few sources to say anything about the pattern...”
- **Narrow posting window:** at least 70% of the articles fall within one two-hour window **and** the full time span between the oldest and newest article is at least 6 hours.
- **Otherwise:** “No unusual pattern was found in these N articles from M sources.”

The “too few” and “no unusual pattern” sentences include the article and distinct-source counts. Source age does not currently affect which sentence is selected. The narrow-window sentence describes timing only; it is not a finding about intent or truth.

## Proof and transparency

- The evidence table lists the analysed articles, source name and domain, India/International tag, headline, IST publication time, snippet, and a link to the article.
- Article links open in a new tab.
- Search details show the entered query, cleaned query, provider, parameters, selected time window, and search time. API keys are not shown.
- The collapsible raw response displays the GNews reply received by the app.
- JSON and CSV buttons download the article evidence and search details.
- The Google cross-check button opens a Google News search for the original query.
- Each indicator includes a “How this was calculated” note identifying the relevant domains or article numbers.

## India-first sourcing

The GNews request uses `country=in` and English. The app marks a result “India” when GNews reports the source country as `in`, the domain matches a publisher in `config.py`, or the domain ends in `.in`. Other results are tagged “International.”

Indian-tagged results are ranked first, then other results fill the remaining places, up to 6 analysed articles. These are origin tags only, not quality judgments.

## Tech stack

| Technology | What it is used for |
|---|---|
| Python | Fetching, analysis, and app behavior |
| Flask | Web server, page route, and analysis endpoints |
| GNews API | News search results |
| RDAP | Domain registration-date lookups |
| tldextract | Finding registrable domains for RDAP lookups; configured offline with its bundled suffix list |
| HTML | Page structure and evidence table |
| CSS | Existing page design and bar charts |
| JavaScript | Search actions, result display, and evidence downloads |
| python-dotenv | Loading `GNEWS_API_KEY` from a local `.env` file |
| Vercel | Deployment routing is configured in `vercel.json`; the app is not necessarily deployed yet |

## Project structure

```text
.
├── api/
│   └── index.py             Vercel entry point that imports the Flask app
├── static/
│   ├── app.js               Search, rendering, cross-check, and downloads
│   └── style.css            Page colors, layout, and chart styles
├── templates/
│   └── index.html           The single-page app template
├── app.py                   Flask app and indicator calculations
├── config.py                Article limit and Indian publisher domains
├── news_source.py           GNews requests, retries, and article normalization
├── requirements.txt         Python package dependencies
├── .env.example             Environment variable name and placeholder
├── .gitignore               Local files excluded from Git
└── vercel.json              Vercel function and route configuration
```

The local `.env` file and `.venv/` environment are not included in this tree because they are private/local files.

## Install and run

Use Python 3.10 or newer. Open a terminal in the project folder and install the listed packages:

```powershell
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`, then replace its placeholder with your GNews API key:

```text
GNEWS_API_KEY=your_key_here
```

Start the app:

```powershell
python app.py
```

Open <http://127.0.0.1:5000>. Select **Use demo data** to view the built-in example without making a news search.

## Example searches

These short searches returned results on the free plan when checked on September 28, 2026:

- `India cricket`
- `India weather`
- `ISRO`

News changes constantly, so a search that worked earlier may return no articles later. Short keywords work best; the app automatically tries wider date windows.

## Known limitations

- The free GNews plan may delay articles by up to 12 hours, as indicated by the provider.
- Only up to 6 articles are analysed, selected from up to 10 GNews candidates.
- A source-age result may be “Unknown” when RDAP does not provide a usable registration date.
- News agencies such as ANI and PTI provide copy to multiple outlets; shared wording by itself does not mean coordination.
- These results are descriptive indicators, not proof of coordination, intent, or whether a claim is true.
- The final sentence uses article count and posting-time thresholds; source age is displayed but does not currently affect that sentence.

## Possible future improvements

- Add tests for article parsing, similarity grouping, and the final-sentence thresholds.
- Show clearer explanations when GNews returns an API error or reaches a plan limit.
- Let readers compare the current search with another date range.
- Improve accessible text descriptions for the visual bar charts.
- Add optional user-selected source and time filters without scoring individual outlets.
