#!/usr/bin/env python3
"""
munster_bot.py

Wikipedia-based Munster match thread poster.

Usage:
  python munster_bot.py            -> normal run (posts only if within 3h window or live)
  python munster_bot.py --force    -> force post the next match (for testing)
  python munster_bot.py --debug    -> run in debug mode (no posting) and print parsed match info

Dependencies:
  pip install requests beautifulsoup4 python-dateutil praw
"""

import os
import re
import json
import time
import sys
from datetime import datetime, timedelta
import pytz
import requests
from bs4 import BeautifulSoup

try:
    from dateutil import parser as dateparser
except Exception:
    dateparser = None

# ---------- CONFIG ----------
TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
MATCH_HISTORY_FILE = "posted.json"
POST_BEFORE_HOURS = 3   # post 3 hours before kickoff
IST = pytz.timezone("Europe/Dublin")
WIKIPEDIA_API_SEARCH = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": os.getenv("USER_AGENT", "MunsterKickoffBot/1.0 (+https://github.com/yourrepo)")}

# competitions we will try to recognise for standings inclusion
STANDINGS_KEYWORDS = ["United Rugby Championship", "URC", "Champions Cup", "Heineken Champions Cup", "Challenge Cup"]

# Known broadcast strings to show as "Likely"
LIKELY_BROADCAST = "Premier Sports / TG4 / URC.tv / RTÉ"

# reddit flair id if you want to automatically apply (optional)
FLAIR_ID = os.getenv("FLAIR_ID", None)

# ---------- helpers ----------
def safe_get(url, timeout=20, params=None):
    try:
        r = requests.get(url, timeout=timeout, params=params, headers=HEADERS)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"❌ HTTP error fetching {url}: {e}")
        return None

def load_posted():
    if not os.path.exists(MATCH_HISTORY_FILE):
        return []
    try:
        with open(MATCH_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_posted(posted):
    with open(MATCH_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(posted, f, indent=2)

def parse_date_text(date_text):
    """Parse a date/time string into aware UTC datetime. Uses dateutil if available, else tries common formats."""
    if not date_text or not date_text.strip():
        return None
    date_text = date_text.strip()
    # try dateutil first
    if dateparser:
        try:
            dt = dateparser.parse(date_text, dayfirst=True)
            if dt and dt.tzinfo is None:
                # assume IST (Europe/Dublin) if no tz provided
                dt = IST.localize(dt)
            if dt:
                return dt.astimezone(pytz.utc)
        except Exception:
            pass
    # fallback formats
    fmts = [
        "%d %B %Y %H:%M", "%d %b %Y %H:%M",
        "%A %d %B %Y %H:%M", "%A %d %b %Y %H:%M",
        "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(date_text, fmt)
            dt = IST.localize(dt)
            return dt.astimezone(pytz.utc)
        except Exception:
            continue
    return None

# ---------- Wikipedia helpers ----------
def wiki_search_pages(query, limit=10):
    """Use MediaWiki API to search for relevant pages."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "format": "json"
    }
    r = safe_get(WIKIPEDIA_API_SEARCH, params=params)
    if not r:
        return []
    data = r.json()
    results = [s["title"] for s in data.get("query", {}).get("search", [])]
    return results

def wiki_get_html_by_title(title):
    """Fetch the HTML content of a Wikipedia page by title."""
    url = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")
    r = safe_get(url)
    if not r:
        return None
    return r.text

def extract_wikitable_fixtures(html):
    """
    Parse provided HTML and try to extract fixtures from wikitable(s).
    Return list of dicts: {date_text, datetime_utc, competition, home, away, venue, note, source_url}
    """
    soup = BeautifulSoup(html, "html.parser")
    fixtures = []

    # Find all tables (many season pages use class 'wikitable' for fixtures)
    tables = soup.select("table.wikitable, table")
    for t in tables:
        # quick heuristic: does this table contain team names and dates?
        txt = t.get_text(" ", strip=True)
        if TEAM_NAME.lower() not in txt.lower():
            # might still be relevant (team season pages have only Munster rows), but skip obvious non-fixtures
            pass
        # try read rows
        headers = [th.get_text(" ", strip=True).lower() for th in t.select("th")]
        rows = t.select("tr")
        for tr in rows[1:]:
            cols = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if not cols:
                continue
            # heuristics: find columns containing a date, and an opponent team string
            combined = " ".join(cols)
            if TEAM_NAME.lower() not in combined.lower() and "munster" not in combined.lower():
                # Some season pages only list opponents without repeating "Munster"; check if opponent present and date present
                pass
            # Try to detect opponent and date
            date_text = None; opponent = None; venue = None; comp = None; note = None
            # Many fixture tables: Date | Opponent | Venue | Score | Competition
            # We will scan cols for a date-like column and a team-like column
            for c in cols:
                # is there a month name?
                if re.search(r'\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b', c, re.I):
                    date_text = c
                    continue
                # time included e.g. '19:35' or '19:35 BST'
                if re.search(r'\d{1,2}:\d{2}', c):
                    if date_text:
                        date_text = date_text + " " + c
                        continue
                # opponent detection: contains vs or v. or just a team name (we look for 'Leinster', 'Ulster', etc.)
                if re.search(r'\b(vs|v\.|v|versus)\b', c, re.I) or re.search(r'\b(Leinster|Ulster|Connacht|Edinburgh|Glasgow|Cardiff|Bulls|Stormers|Munster|Benetton|Bourg|La Rochelle|Toulouse|Clermont)\b', c, re.I):
                    opponent = c
                    continue
            # If we found something
            if date_text or opponent:
                # Try to split opponent to home/away vs Munster
                home = TEAM_NAME; away = None
                if opponent:
                    # normalize opponent string by removing 'v', 'vs', 'vs.' etc.
                    op = re.sub(r'\b(vs\.?|v\.|versus|vs)\b', '', opponent, flags=re.I).strip()
                    # If the row lists 'Munster vs Leinster' it will include both names; extract other team
                    parts = [p.strip() for p in re.split(r'–|-|—|vs\.?|v\.?|versus', opponent, flags=re.I) if p.strip()]
                    if len(parts) >= 2:
                        # find which part is not Munster
                        if TEAM_NAME.lower() in parts[0].lower():
                            away = parts[1]
                        else:
                            # if Munster not present, assume Munster plays parts[0]
                            away = parts[0]
                    else:
                        # fallback: take whole as away if it doesn't include 'Munster'
                        away = op if TEAM_NAME.lower() not in op.lower() else None

                # venue guess
                # take a column that contains 'Stadium', 'Park', 'Ground', 'Arena'
                for c in cols:
                    if re.search(r'\b(Stadium|Park|Ground|Arena|Field|Arena|Croke Park|Thomond)\b', c, re.I):
                        venue = c
                        break

                # competition guess: presence of cup or URC words
                for c in cols:
                    m = re.search(r'(United Rugby Championship|URC|Champions Cup|Challenge Cup|European)', c, re.I)
                    if m:
                        comp = m.group(1)
                        break

                fixtures.append({
                    "date_text": date_text or "",
                    "datetime_utc": parse_date_text(date_text) if date_text else None,
                    "competition": comp or "",
                    "home": home,
                    "away": away or "",
                    "venue": venue or "",
                    "note": "",
                    "source_html": t.prettify()[:2000]
                })
    return fixtures

def discover_fixtures_from_wikipedia():
    """
    Try a set of sensible Wikipedia searches to find Munster fixtures pages (season pages, URC pages).
    Returns a list of fixtures (possibly with duplicates) sorted by datetime where present.
    """
    candidates = []
    queries = [
        "Munster Rugby fixtures",
        "Munster season fixtures",
        "Munster Rugby 2025 fixtures",
        "Munster 2025–26 season",
        "2025–26 United Rugby Championship fixtures",
        "United Rugby Championship 2025–26",
        "Munster Rugby 2024–25 season",
        "Munster fixtures 2025"
    ]
    found_titles = set()
    for q in queries:
        print(f"🔎 Searching Wikipedia for: {q}")
        titles = wiki_search_pages(q, limit=8)
        for t in titles:
            if t in found_titles:
                continue
            found_titles.add(t)
            print(f"  → candidate page: {t}")
            html = wiki_get_html_by_title(t)
            if not html:
                continue
            fixtures = extract_wikitable_fixtures(html)
            for f in fixtures:
                # attach source page title for traceability
                f["source_page"] = t
                candidates.append(f)
            # small pause to be kind to Wikipedia
            time.sleep(0.5)

    # also try the team main page
    team_html = wiki_get_html_by_title("Munster_Rugby")
    if team_html:
        fxs = extract_wikitable_fixtures(team_html)
        for f in fxs:
            f["source_page"] = "Munster_Rugby"
            candidates.append(f)

    # Deduplicate by (away, datetime) and only keep future/present & valid
    now = datetime.now(pytz.utc)
    unique = {}
    for f in candidates:
        key = (f.get("away","").lower(), str(f.get("datetime_utc")))
        # accept also if datetime missing but has date_text
        if key not in unique:
            unique[key] = f

    fixtures_list = list(unique.values())

    # Keep only those with either datetime_utc in future (or none but with a date_text)
    upcoming = []
    for f in fixtures_list:
        dt = f.get("datetime_utc")
        if dt:
            if dt >= now - timedelta(days=1):  # include recent live if today
                upcoming.append(f)
        else:
            # keep if date_text present (we'll try to parse heuristically later)
            if f.get("date_text"):
                upcoming.append(f)

    # sort by datetime if present, else keep at end
    def sort_key(x):
        if x.get("datetime_utc"):
            return x["datetime_utc"]
        return datetime.max.replace(tzinfo=pytz.utc)
    upcoming.sort(key=sort_key)
    print(f"🔔 Discovered {len(upcoming)} candidate fixture(s) from Wikipedia search.")
    return upcoming

# ---------- standings extraction ----------
def find_standings_for_competition(competition_keyword):
    """
    Attempt to find a Wikipedia page with standings table for the given competition keyword (e.g. URC or Champions Cup).
    Returns list of rows (dicts) or None.
    """
    if not competition_keyword:
        return None
    # map common names to search queries
    if "URC" in competition_keyword or "United Rugby" in competition_keyword:
        queries = ["United Rugby Championship table", "2025–26 United Rugby Championship table", "United Rugby Championship standings"]
    elif "Champions Cup" in competition_keyword or "Heineken" in competition_keyword:
        queries = ["Heineken Champions Cup table", "2025–26 European Rugby Champions Cup table"]
    elif "Challenge Cup" in competition_keyword:
        queries = ["European Rugby Challenge Cup table", "2025–26 European Rugby Challenge Cup table"]
    else:
        queries = [competition_keyword + " table"]

    for q in queries:
        print(f"🔎 Searching standings for: {q}")
        titles = wiki_search_pages(q, limit=6)
        for t in titles:
            html = wiki_get_html_by_title(t)
            if not html:
                continue
            s = BeautifulSoup(html, "html.parser")
            # find wikitable that looks like standings: headers include 'Pos' 'Team' 'Pld' 'Pts'
            tables = s.select("table.wikitable")
            for tbl in tables:
                headers = [th.get_text(" ", strip=True).lower() for th in tbl.select("th")]
                if any(h in " ".join(headers) for h in ("pos", "team", "pld", "pts")):
                    # parse this standings table
                    rows = []
                    for tr in tbl.select("tr")[1:]:
                        cols = [td.get_text(" ", strip=True) for td in tr.select("td")]
                        if not cols:
                            continue
                        # try to align: Pos, Team, Pld, W, D, L, Pts (many variants)
                        row = {
                            "raw": cols
                        }
                        rows.append(row)
                    if rows:
                        print(f"✅ Found standings table on {t}")
                        return {"title": t, "rows": rows, "html": tbl.prettify()[:2000]}
    return None

# ---------- reddit posting ----------
def reddit_client():
    import praw
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT", "MunsterKickoffBot/1.0")
    )

def format_title(match):
    # Title: short day (Sat), dd Mon YYYY @ HH:MMhrs (IST)
    dt_ist = match["datetime"].astimezone(IST) if match.get("datetime") else None
    if dt_ist:
        date_part = dt_ist.strftime("%a %d %b %Y @ %H:%Mhrs (IST)")
    else:
        date_part = "TBC"
    return f"Match Thread: {TEAM_NAME} vs. {match.get('away','TBC')} ({match.get('competition','Fixture')}) - {date_part} - {match.get('venue','TBC')}"

def format_standings_md(standings):
    # standings['rows'] are raw lists; try to make a simple markdown table showing first 8 rows as best-effort
    if not standings or not standings.get("rows"):
        return ""
    rows = standings["rows"]
    md = []
    md.append("📊 **Current Standings:**")
    md.append("")
    # header guess
    md.append("| Pos | Team | Pld | W | D | L | Pts |")
    md.append("|:---:|:---|:---:|:---:|:---:|:---:|:---:|")
    # iterate
    for r in rows[:10]:
        cols = r.get("raw", [])
        # try to extract position and team and points from common positions in table
        pos = cols[0] if len(cols) > 0 else ""
        team = cols[1] if len(cols) > 1 else cols[0] if cols else ""
        pld = cols[2] if len(cols) > 2 else ""
        pts = cols[-1] if len(cols) >= 1 else ""
        md.append(f"| {pos} | {team} | {pld} |  |  |  | {pts} |")
    md.append("")
    return "\n".join(md)

def format_body(match, standings_md=None):
    dt_ist = match["datetime"].astimezone(IST) if match.get("datetime") else None
    kickoff_line = dt_ist.strftime("%A %d %B %Y @ %H:%M (IST)") if dt_ist else "TBC"
    lines = []
    lines.append(f"🏉 **Kickoff:** {kickoff_line} - {match.get('venue','TBC')}")
    lines.append("")
    lines.append(f"🏆 **Competition:** {match.get('competition') or 'Fixture'}")
    lines.append("")
    lines.append(f"📺 **Likely broadcast (UK/IE):** {LIKELY_BROADCAST}")
    lines.append("")
    if standings_md:
        lines.append(standings_md)
    lines.append("")
    lines.append("**Stand Up And Fight! 💪🔴**")
    lines.append("")
    lines.append("---")
    lines.append("_Automated by /u/MunsterKickoff 🤖_")
    return "\n".join(lines)

def post_match_thread(match, standings_md=None, debug=False):
    r = reddit_client()
    sr = r.subreddit(SUBREDDIT)
    title = format_title(match)
    body = format_body(match, standings_md)
    print("---- Ready to post with following content ----")
    print(title)
    print(body[:1000])
    print("---- End preview ----")
    if debug:
        print("Debug mode: not posting to Reddit.")
        return None
    # submit
    submission = sr.submit(title, selftext=body)
    try:
        if FLAIR_ID:
            submission.flair.select(FLAIR_ID)
    except Exception:
        pass
    try:
        submission.mod.distinguish(sticky=True)
    except Exception:
        pass
    print(f"✅ Posted: {submission.id}")
    # record posted by match url or unique string
    posted = load_posted()
    key = match.get("source_page", "") + "|" + (match.get("away","") or "")
    posted.append(key)
    save_posted(posted)
    return submission.id

# ---------- main runner ----------
def pick_next_match(fixtures):
    """Pick the next upcoming fixture from fixtures (list) where datetime is soonest >= now."""
    now = datetime.now(pytz.utc)
    # filter those with datetime if possible
    with_dt = [f for f in fixtures if f.get("datetime_utc")]
    without_dt = [f for f in fixtures if not f.get("datetime_utc")]
    with_dt_sorted = sorted(with_dt, key=lambda x: x["datetime_utc"])
    for f in with_dt_sorted:
        if f["datetime_utc"] >= now - timedelta(hours=1):
            # return as soon as a future/present one found
            # Normalize keys to match our match dict
            return {
                "datetime": f["datetime_utc"],
                "competition": f.get("competition") or "",
                "away": f.get("away") or "",
                "venue": f.get("venue") or "",
                "source_page": f.get("source_page"),
                "source": "wikipedia",
                "extra": f
            }
    # fallback to first with date_text but no parse
    if without_dt:
        f = without_dt[0]
        dt = None
        if f.get("date_text"):
            dt = parse_date_text(f["date_text"])
        return {
            "datetime": dt or datetime.now(pytz.utc),
            "competition": f.get("competition") or "",
            "away": f.get("away") or "",
            "venue": f.get("venue") or "",
            "source_page": f.get("source_page"),
            "source": "wikipedia",
            "extra": f
        }
    return None

def main(force=False, debug=False):
    print("🔔 Munster Wikipedia Match Bot starting...")
    fixtures = discover_fixtures_from_wikipedia()
    if not fixtures:
        print("❌ No fixtures discovered. Exiting.")
        return
    match = pick_next_match(fixtures)
    if not match:
        print("❌ Couldn't pick a next upcoming match.")
        return
    print("📌 Next match candidate:", match["away"], "on", match["datetime"])

    # check posted
    posted = load_posted()
    key = match.get("source_page","") + "|" + (match.get("away","") or "")
    if key in posted and not force:
        print("ℹ️ This match appears to already have been posted. Exiting.")
        return

    # determine posting time (3 hours before kick-off)
    post_time = match["datetime"] - timedelta(hours=POST_BEFORE_HOURS)
    now = datetime.now(pytz.utc)
    is_live = False
    # if datetime within a small window or appears live in extra text, post immediately
    extra = match.get("extra", {})
    if extra:
        if extra.get("is_live"):
            is_live = True
    if force or is_live or now >= post_time or abs((now - match["datetime"]).total_seconds()) < 3600:
        # try to get standings if competition relevant
        standings_md = None
        comp = match.get("competition","") or ""
        if any(k.lower() in comp.lower() for k in STANDINGS_KEYWORDS):
            standings = find_standings_for_competition(comp)
            standings_md = format_standings_md(standings) if standings else None
        # post
        post_match_thread(match, standings_md=standings_md, debug=debug)
    else:
        print(f"⏳ Not time yet. Kickoff (UTC): {match['datetime']} | Post time (UTC): {post_time}")
        return

if __name__ == "__main__":
    force_flag = ("--force" in sys.argv)
    debug_flag = ("--debug" in sys.argv)
    main(force=force_flag, debug=debug_flag)
