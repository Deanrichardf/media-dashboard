#!/usr/bin/env python3
"""
Books and Podcasts - Weekly Recommendations Updater
Run weekly via Windows Task Scheduler.

Fetches recent podcast episodes via iTunes API + RSS and fresh articles
via RSS, writes recommendations.json, then commits and pushes to GitHub.
"""
import json, subprocess, sys, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
import feedparser, requests

REPO = Path(__file__).parent

# ── Podcast shows ────────────────────────────────────────────────────────────
# 'rss' overrides iTunes lookup (use when the Apple ID doesn't return feedUrl)
PODCAST_SHOWS = [
    {'show': 'The Rest Is History',    'id': '1537788786', 'by': 'Tom Holland & Dominic Sandbrook', 'tags': ['history']},
    {'show': 'Triggernometry',         'id': '1375568988', 'by': 'Kisin & Foster',                  'tags': ['politics']},
    {'show': 'We Have Ways',           'id': '1457552694', 'by': 'James Holland & Al Murray',       'tags': ['history', 'ww2']},
    {'show': 'Modern Wisdom',          'id': '1347973549', 'by': 'Chris Williamson',                'tags': ['learning', 'philosophy']},
    {'show': 'History Hit',            'id': '1437402037', 'by': 'Dan Snow',                        'tags': ['history'],
     'rss': 'https://feeds.acast.com/public/shows/c939f8d1-c4bc-478e-8bb9-e5343f9a7ab5'},
    {'show': 'Intelligence Squared',   'id': '275541834',  'by': 'IQ2 Debates',                    'tags': ['politics', 'philosophy'],
     'rss': 'https://feeds.megaphone.fm/PNP1207584390'},
    {'show': 'Philosophize This!',     'id': '659155419',  'by': 'Stephen West',                   'tags': ['philosophy']},
    {'show': 'In Our Time',            'id': '73330895',   'by': 'Melvyn Bragg',                   'tags': ['history', 'learning']},
    {'show': 'EconTalk',               'id': '135066958',  'by': 'Russ Roberts',                   'tags': ['learning']},
    {'show': 'Cautionary Tales',       'id': '1484511501', 'by': 'Tim Harford',                    'tags': ['history', 'learning'],
     'rss': 'https://www.omnycontent.com/d/playlist/e73c998e-6e60-432f-8610-ae210140c5b1/c0ae8c6e-22f0-4e9b-ac1c-ae390037ac53/7f5a4714-6b10-4ccf-a424-ae390037ac70/podcast.rss'},
    {'show': 'Making Sense',           'id': '733163012',  'by': 'Sam Harris',                     'tags': ['philosophy', 'science']},
    {'show': 'Dan Carlin Hardcore History', 'id': '173001861', 'by': 'Dan Carlin',                 'tags': ['history']},
]

# ── Article RSS feeds ────────────────────────────────────────────────────────
ARTICLE_FEEDS = [
    {'source': 'Smithsonian',       'url': 'https://www.smithsonianmag.com/rss/history/',         'tags': ['history']},
    {'source': 'Aeon',              'url': 'https://aeon.co/feed.rss',                             'tags': ['philosophy', 'learning']},
    {'source': 'Quanta Magazine',   'url': 'https://api.quantamagazine.org/feed/',                 'tags': ['science', 'learning']},
    {'source': 'The Spectator',     'url': 'https://www.spectator.co.uk/feed/',                    'tags': ['politics']},
    {'source': 'UnHerd',            'url': 'https://unherd.com/feed/',                             'tags': ['politics', 'philosophy']},
    {'source': 'The Critic',        'url': 'https://thecritic.co.uk/feed/',                        'tags': ['history', 'politics']},
    {'source': 'Big Think',         'url': 'https://bigthink.com/feed/',                           'tags': ['philosophy', 'learning']},
    {'source': 'Nautilus',          'url': 'https://nautil.us/feed/',                              'tags': ['science', 'philosophy']},
    {'source': 'National Geographic','url': 'https://www.nationalgeographic.com/history/rss',      'tags': ['history', 'geography']},
    {'source': 'Atlas Obscura',     'url': 'https://www.atlasobscura.com/feeds/latest',            'tags': ['geography', 'history']},
    {'source': 'Hoover Institution','url': 'https://www.hoover.org/rss/publications',              'tags': ['history', 'politics']},
    {'source': 'Persuasion',        'url': 'https://www.persuasion.community/feed',                'tags': ['politics', 'philosophy']},
    {'source': 'Engelsberg Ideas',  'url': 'https://engelsbergideas.com/feed/',                    'tags': ['history', 'philosophy']},
    {'source': 'The Free Press',    'url': 'https://www.thefp.com/feed',                           'tags': ['politics']},
    {'source': 'The Daily Signal',  'url': 'https://www.dailysignal.com/feed/',                    'tags': ['politics']},
]

ARTICLES_PER_WEEK = 20
RECENT_PODCASTS_TARGET = 10
LOOKBACK_DAYS = 14   # search this far back for recent episodes
BOOKS_TARGET = 20    # 10/week × 2-week pool rotation

# Open Library queries — each scoped to 2025 publications
BOOK_SEARCHES = [
    {'q': 'subject:history first_publish_year:2025',              'tags': ['history']},
    {'q': 'subject:"historical fiction" first_publish_year:2025', 'tags': ['fiction', 'history']},
    {'q': 'subject:thriller first_publish_year:2025',             'tags': ['thriller']},
    {'q': 'subject:mystery first_publish_year:2025',              'tags': ['mystery']},
    {'q': 'subject:biography first_publish_year:2025',            'tags': ['history', 'learning']},
    {'q': 'subject:politics first_publish_year:2025',             'tags': ['politics']},
    {'q': 'subject:philosophy first_publish_year:2025',           'tags': ['philosophy']},
    {'q': 'subject:science first_publish_year:2025',              'tags': ['science', 'learning']},
]


def get_rss_url(itunes_id: str) -> str | None:
    """Resolve RSS feed URL from Apple Podcast ID via iTunes lookup API."""
    try:
        r = requests.get(
            f'https://itunes.apple.com/lookup?id={itunes_id}&entity=podcast',
            timeout=10
        )
        results = r.json().get('results', [])
        return results[0].get('feedUrl') if results else None
    except Exception:
        return None


def parse_date(entry) -> datetime | None:
    """Parse published date from a feedparser entry."""
    for attr in ('published_parsed', 'updated_parsed'):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def fetch_recent_podcast_episodes() -> list[dict]:
    """Fetch episodes published within LOOKBACK_DAYS from all tracked shows."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    episodes = []

    for meta in PODCAST_SHOWS:
        feed_url = meta.get('rss') or get_rss_url(meta['id'])
        if not feed_url:
            print(f'  ! No RSS for {meta["show"]}', file=sys.stderr)
            continue
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f'  ! Feed error {meta["show"]}: {e}', file=sys.stderr)
            continue

        for entry in feed.entries[:8]:
            pub = parse_date(entry)
            if pub and pub >= cutoff:
                url = entry.get('link') or entry.get('id', '')
                episodes.append({
                    'show': meta['show'],
                    'title': entry.get('title', 'Untitled'),
                    'by':   meta['by'],
                    'tags': meta['tags'],
                    'url':  url,
                })
            if len(episodes) >= RECENT_PODCASTS_TARGET * 2:
                break   # gather extras for variety

    return episodes[:RECENT_PODCASTS_TARGET * 2]


def fetch_articles() -> list[dict]:
    """Fetch recent articles from all tracked publication RSS feeds."""
    articles = []
    seen_urls: set[str] = set()
    per_source = max(2, ARTICLES_PER_WEEK // len(ARTICLE_FEEDS) + 1)

    for meta in ARTICLE_FEEDS:
        try:
            feed = feedparser.parse(meta['url'])
        except Exception as e:
            print(f'  ! Article feed error {meta["source"]}: {e}', file=sys.stderr)
            continue

        count = 0
        for entry in feed.entries:
            url = entry.get('link', '')
            if not url or url in seen_urls:
                continue
            # skip anything that looks like a category/tag page, not an article
            if re.search(r'/tag/|/category/|/author/', url):
                continue
            seen_urls.add(url)
            articles.append({
                'source': meta['source'],
                'title':  entry.get('title', 'Untitled'),
                'tags':   meta['tags'],
                'url':    url,
            })
            count += 1
            if count >= per_source:
                break

    # shuffle so sources are interleaved rather than grouped
    import random
    random.shuffle(articles)
    return articles[:ARTICLES_PER_WEEK]


def fetch_books() -> list[dict]:
    """Fetch 2025-2026 books from Open Library matching user taste profile."""
    import random
    books: list[dict] = []
    seen_titles: set[str] = set()
    seen_authors: dict[str, int] = {}
    per_search = max(3, BOOKS_TARGET // len(BOOK_SEARCHES) + 1)

    for meta in BOOK_SEARCHES:
        try:
            r = requests.get(
                'https://openlibrary.org/search.json',
                params={
                    'q': meta['q'],
                    'limit': 40,
                    'fields': 'title,author_name,first_publish_year,cover_i,isbn,key,language',
                },
                timeout=15,
            )
            docs = r.json().get('docs', [])
        except Exception as e:
            print(f'  ! Books API error ({meta["q"][:35]}): {e}', file=sys.stderr)
            continue

        count = 0
        for doc in docs:
            year = str(doc.get('first_publish_year', ''))
            if year not in ('2025', '2026'):
                continue
            # Language: skip if explicitly non-English
            lang = doc.get('language', [])
            if lang and 'eng' not in lang:
                continue
            title = doc.get('title', '')
            # Quality gate: cover + author + ISBN + sane title + no ALL-CAPS words
            if not (doc.get('cover_i') and doc.get('author_name') and doc.get('isbn')):
                continue
            if not (3 < len(title) < 75):
                continue
            if any(w.isupper() and len(w) > 2 for w in title.split()):
                continue
            if title in seen_titles:
                continue
            author = doc['author_name'][0]
            if seen_authors.get(author, 0) >= 1:
                continue  # one book per author for variety
            seen_titles.add(title)
            seen_authors[author] = seen_authors.get(author, 0) + 1
            ol_key = doc.get('key', '')
            url = f'https://openlibrary.org{ol_key}' if ol_key else ''
            if not url:
                continue
            books.append({
                'title':  title,
                'author': author,
                'year':   year,
                'tags':   meta['tags'],
                'url':    url,
                'cover':  f'https://covers.openlibrary.org/b/id/{doc["cover_i"]}-M.jpg',
            })
            count += 1
            if count >= per_search:
                break

    random.shuffle(books)
    return books[:BOOKS_TARGET]


def git_commit_push(date_str: str):
    for cmd in [
        ['git', 'add', 'recommendations.json'],
        ['git', 'commit', '-m', f'chore: update recommendations {date_str}'],
        ['git', 'push'],
    ]:
        subprocess.run(cmd, cwd=str(REPO), check=True, capture_output=True)


def main():
    now = datetime.now(timezone.utc)
    print(f'[{now:%Y-%m-%d %H:%M}] Fetching recommendations...')

    rp = fetch_recent_podcast_episodes()
    ar = fetch_articles()
    bk = fetch_books()

    print(f'  Podcasts: {len(rp)}  Articles: {len(ar)}  Books: {len(bk)}')

    out = {
        'generated': now.isoformat(),
        'rp': rp,
        'ar': ar,
        'books': bk,
    }

    path = REPO / 'recommendations.json'
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f'  OK Written recommendations.json')

    try:
        git_commit_push(now.strftime('%Y-%m-%d'))
        print('  OK Pushed to GitHub')
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if e.stderr else ''
        # "nothing to commit" is not a real error
        if 'nothing to commit' in stderr or 'nothing added' in stderr:
            print('  ─ Nothing changed, skipping push')
        else:
            print(f'  ! Git error: {stderr}', file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
