# munster_bot.py
# Full rewrite: robust RugbyPass scraping (match page + Teams tab), time parsing, and Reddit posting.
# Replace your old munster_bot.py with this file.

import os
import re
import json
import pytz
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import praw

# ---------------- CONFIG ----------------
TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
MATCH_HISTORY_FILE = "posted.json"
FIXTURES_URL = "https://www.rugbypass.com/teams/munster/fixtures-results/"
FLAIR_ID = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"   # match-thread flair id you gave
POST_BEFORE_HOURS = 4
# ---------------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

IST = pytz.timezone("Europe/Dublin")

# ---------------- helpers ----------------
def safe_get(url, timeout=20):
    try:
        r = requests.get(url, timeout=timeout, headers=HEADERS)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"❌ Error fetching URL {url}: {e}")
        return None

def month_name_to_number(name):
    try:
        return datetime.strptime(name[:3], "%b").month
    except Exception:
        # fallback simple map
        m = {
            "January":1, "February":2, "March":3, "April":4, "May":5, "June":6,
            "July":7, "August":8, "September":9, "October":10, "November":11, "December":12
        }
        return m.get(name, 0)

def parse_datetime_from_line(line):
    # Remove ordinal suffixes (1st, 2nd, 3rd, 10th)
    clean = re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', line, flags=re.I)
    # Regex to capture e.g. "Fri 10 October 2025, 07:45pm BST" or "10 October 2025 19:45" etc.
    regex = re.compile(
        r'(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})[,|\s]*'
        r'(?:(?P<hour>\d{1,2}):(?P<minute>\d{2})(?P<ampm>am|pm|AM|PM)?)?'
        r'(?:\s*(?P<tz>[A-Za-z]{2,5}))?',
        flags=re.I
    )
    m = regex.search(clean)
    if not m:
        return None  # couldn't parse
    day = int(m.group('day'))
    month = month_name_to_number(m.group('month'))
    year = int(m.group('year'))
    hour = m.group('hour')
    minute = m.group('minute')
    ampm = m.group('ampm')
    tz_abbr = m.group('tz') or ""

    if hour and minute:
        hour = int(hour)
        minute = int(minute)
        if ampm:
            ampm = ampm.lower()
            if ampm == 'pm' and hour != 12:
                hour += 12
            if ampm == 'am' and hour == 12:
                hour = 0
    else:
        # no time provided — assume 19:45 local (common) OR leave None (we'll treat as today)
        hour = None
        minute = None

    # Determine timezone mapping (simple)
    tz_map = {
        "BST": "Europe/London",
        "GMT": "Europe/London",
        "WET": "Europe/London",
        "CET": "Europe/Paris",
        "SAST": "Africa/Johannesburg",
        "NZST": "Pacific/Auckland",
        "AEST": "Australia/Sydney",
        "IST": "Europe/Dublin",  # user wants IST
        "UTC": "UTC"
    }
    tz_name = tz_map.get(tz_abbr.upper(), None)

    try:
        if hour is None:
            # no time supplied -> set to 00:00 temporarily (we'll treat as 'today' if needed)
            dt_naive = datetime(year, month, day, 0, 0)
            if tz_name:
                tz = pytz.timezone(tz_name)
            else:
                tz = IST
            dt_local = tz.localize(dt_naive)
        else:
            dt_naive = datetime(year, month, day, hour, minute)
            if tz_name:
                tz = pytz.timezone(tz_name)
            else:
                # default to Ireland time if not specified
                tz = IST
            dt_local = tz.localize(dt_naive)
        dt_utc = dt_local.astimezone(pytz.utc)
        return dt_utc
    except Exception as e:
        print(f"❌ Failed to build datetime from '{line}': {e}")
        return None

def extract_lineup_from_teams_text(text, team_name):
    # Find the block for the team_name and extract starter names until "Substitutes"
    # text is plain text (soup.get_text())
    # We use first occurrence of team_name then next team header to slice block
    idx = text.find(team_name)
    if idx == -1:
        return []
    # find where the next "##" or next team header occurs after idx
    # we'll search for two consecutive newlines followed by capitalized word-level headings
    tail = text[idx:]
    # find next occurrence of two newlines followed by a capitalized word and newline + a digit or "##"
    # simpler: find next occurrence of '\n##' or next team name by scanning for two-letter words + numbers (we'll use next "##" or end)
    next_team_pos = None
    # Attempt to find '##' (RugbyPass page included '##  Edinburgh')
    m = re.search(r'\n##\s+', tail)
    if m:
        next_team_pos = m.start()
        block = tail[:next_team_pos]
    else:
        # fallback: cut 600 chars after team_name (should include starters)
        block = tail[:800]
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    starters = []
    for l in lines:
        # stop when substitutes heading hit
        if re.match(r'^Substitutes', l, flags=re.I) or re.match(r'^###\s*Substitutes', l, flags=re.I):
            break
        # skip lines that are single numbers
        if re.fullmatch(r'\d+', l):
            continue
        # skip pure headers
        if l.lower() in (team_name.lower(), "munster", "edinburgh"):
            continue
        # skip 'Who will win?' and similar
        if l.lower().startswith('who will'):
            break
        # Accept lines that look like names (two or more words, or a single capitalised name)
        if len(l.split()) >= 2 and re.match(r'^[A-Za-z\'\-\.\s]+$', l):
            # avoid lines like "1 Milne" which contain a digit (already filtered), but check again
            if any(char.isdigit() for char in l):
                continue
            starters.append(l)
    # final safety: if we detected concatenated condensed line like "1 Milne 2 Barron 3 Jager ..." we also search for patterns " \d+ ([A-Za-z].+?) "
    if len(starters) < 15:
        # attempt to find "1 Milne 2 Barron ..." condensed pattern
        condensed = re.findall(r'\d+\s+([A-Z][a-zA-Z\'\-\.\s]+?)(?=\s+\d+\s+|$)', block)
        if condensed:
            # clean entries
            condensed2 = [c.strip() for c in condensed if len(c.strip().split()) >= 1]
            if len(condensed2) >= len(starters):
                starters = condensed2
    # Return first 15 starters if available
    return starters[:15]

# ---------------- scraping ----------------
def find_next_munster_match():
    print("🔎 Fetching Munster fixtures list from RugbyPass...")
    r = safe_get(FIXTURES_URL)
    if not r:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    # find candidate links to live/fixtures (href contains '/live/' or '/live')
    anchors = soup.select("a[href*='/live/'], a[href*='/live']")
    seen = set()
    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        # normalize URL
        if href.startswith("http"):
            full = href.split("?")[0]
        else:
            full = "https://www.rugbypass.com" + href.split("?")[0]
        # quick filter: link text or href should include 'munster' or both team names; favor first matching 'munster'
        if "munster" not in full.lower() and TEAM_NAME.lower() not in (a.get_text(" ", strip=True).lower()):
            continue
        if full in seen:
            continue
        seen.add(full)
        # check not already posted
        if already_posted_url(full):
            continue
        # Return first suitable match (most immediate/upcoming)
        print(f"✅ Next match candidate: {full}")
        return full
    print("❌ No upcoming un-posted Munster match found on fixtures page.")
    return None

def scrape_match_and_teams(match_url):
    print(f"⚙️ Scraping match page: {match_url}")
    r = safe_get(match_url)
    if not r:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n", strip=True)

    # === Teams ===
    # try CSS first (if present)
    home = None
    away = None
    sel_home = soup.select_one(".fixture__team--home .fixture__team-name")
    sel_away = soup.select_one(".fixture__team--away .fixture__team-name")
    if sel_home and sel_away:
        home = sel_home.get_text(strip=True)
        away = sel_away.get_text(strip=True)
    else:
        # fallback: try to parse title/header
        title = soup.select_one("h1")
        if title and " vs " in title.get_text():
            t = title.get_text(strip=True)
            parts = [p.strip() for p in re.split(r'\s+v(?:s|ersus)\.?\s+|\s+vs\.?\s+', t, flags=re.I)]
            if len(parts) >= 2:
                home, away = parts[0], parts[1]

    if not home or not away:
        # fallback: try to find two team names from top area
        top_text = "\n".join(text.splitlines()[:120])
        found = re.findall(r'\n([A-Z][A-Za-z\'\s\-]{2,30})\n', top_text)
        if found and len(found) >= 2:
            home, away = found[0], found[1]

    home = home or "Munster"
    away = away or "Opponent"

    # === Competition, date, venue ===
    # Try to find the match details region
    competition = None
    venue = "TBC"
    kickoff_dt_utc = None
    # Search for a line containing month name + year
    month_regex = re.compile(r'\b(January|February|March|April|May|June|July|August|September|October|November|December|' +
                             r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b', flags=re.I)
    lines = text.splitlines()
    date_line = None
    for i, line in enumerate(lines[:300]):  # top part of page
        if month_regex.search(line) and re.search(r'\d{4}', line):
            # likely the date line
            date_line = line.strip()
            # also try to pick competition & venue from nearby lines
            # venue likely in next 1-4 lines
            for j in range(i, min(i+6, len(lines))):
                ln = lines[j].strip()
                if ln and 'Virgin' in ln or 'Park' in ln or 'Stadium' in ln or 'Arena' in ln or 'Stadium' in ln:
                    venue = ln
                    break
            # competition: look upward a bit
            for k in range(max(0, i-6), i+1):
                ln2 = lines[k].strip()
                if 'Championship' in ln2 or 'Champions' in ln2 or 'United Rugby' in ln2 or 'URC' in ln2 or 'Friendly' in ln2:
                    competition = ln2
                    break
            break

    if date_line:
        kickoff_dt_utc = parse_datetime_from_line(date_line)
        if not competition:
            # also attempt to find a competition line near "Match Details"
            for i, line in enumerate(lines):
                if 'Match Details' in line:
                    # check a few lines after
                    for j in range(i, min(i+8, len(lines))):
                        ln = lines[j].strip()
                        if ln and (('United Rugby' in ln) or ('Championship' in ln) or ('Champions' in ln) or ('Challenge Cup' in ln)):
                            competition = ln
                            break
                    break

    # If no parsed kickoff (e.g. live page without time or parsing failed) -> treat as live/now
    is_live = False
    # detect LIVE on the page near top
    top_chunk = "\n".join(lines[:40])
    if re.search(r'\bLIVE\b', top_chunk, re.I) or re.search(r'\blive\b', top_chunk):
        is_live = True

    if not kickoff_dt_utc and is_live:
        kickoff_dt_utc = datetime.now(pytz.utc)

    # === Find teams URL (Teams tab) and scrape lineups ===
    teams_url = None
    # prefer explicit Teams tab link
    teams_anchor = soup.find('a', string=re.compile(r'\bTeams\b', re.I))
    if teams_anchor and teams_anchor.get("href"):
        href = teams_anchor.get("href")
        if href.startswith("http"):
            teams_url = href
        else:
            teams_url = "https://www.rugbypass.com" + href
    else:
        # attempt sensible default: append "/teams/" to match_url (preserve query string if present)
        if match_url.endswith("/"):
            teams_url = match_url + "teams/"
        else:
            teams_url = match_url.rstrip("/") + "/teams/"

    lineups = {home: [], away: []}
    teams_page_resp = safe_get(teams_url)
    if teams_page_resp:
        teams_soup = BeautifulSoup(teams_page_resp.text, "html.parser")
        teams_text = teams_soup.get_text("\n", strip=True)
        # Extract lineups for home and away
        home_lineup = extract_lineup_from_teams_text(teams_text, home)
        away_lineup = extract_lineup_from_teams_text(teams_text, away)
        lineups[home] = home_lineup
        lineups[away] = away_lineup
        # try to get venue & competition again from teams page if TBC
        if (not competition) or competition == "Fixture":
            # search for competition words on teams page
            if 'United Rugby Championship' in teams_text or 'URC' in teams_text:
                competition = 'United Rugby Championship'
        if venue == "TBC":
            # attempt from teams page
            # look for common words: Stadium, Park, Arena
            for ln in teams_text.splitlines():
                if any(w in ln for w in ("Stadium", "Park", "Arena", "Ground", "St.")):
                    venue = ln.strip()
                    break

    # final fallback defaults
    competition = competition or "Fixture"
    kickoff_dt_utc = kickoff_dt_utc or datetime.now(pytz.utc)

    # compress competition name (United Rugby Championship -> URC)
    comp_short = competition
    if 'United Rugby Championship' in competition or 'URC' in competition:
        comp_short = 'URC'
    elif 'Champions Cup' in competition or 'Heineken Champions Cup' in competition:
        comp_short = 'Champions Cup'

    # Build final match dict
    match = {
        "url": match_url,
        "teams": f"{home} vs. {away}",
        "home": home,
        "away": away,
        "competition": comp_short,
        "venue": venue,
        "datetime": kickoff_dt_utc,  # aware UTC
        "is_live": is_live,
        "broadcasters": [],  # will fill if present
        "lineups": lineups
    }

    # broadcasters: try to gather
    b_imgs = soup.select(".fixture__broadcasters img")
    if b_imgs:
        for bi in b_imgs:
            alt = bi.get("alt") or bi.get("title") or ""
            if alt:
                match["broadcasters"].append(alt)
    else:
        # fallback parse teams_text for 'TV Guide' region
        for ln in text.splitlines():
            if 'TV' in ln or 'Premier' in ln or 'Sky' in ln or 'Virgin' in ln:
                if 'TV' not in match["broadcasters"]:
                    match["broadcasters"].append(ln.strip())
    print(f"✳️ Parsed match: {match['teams']} | {match['competition']} | Kickoff(UTC): {match['datetime']} | Live: {match['is_live']}")
    print(f" - Venue: {match['venue']}")
    if match['lineups'][home]:
        print(f" - {home} starters: {match['lineups'][home][:6]}...")
    if match['lineups'][away]:
        print(f" - {away} starters: {match['lineups'][away][:6]}...")
    return match

# ---------------- reddit ----------------
def reddit_client():
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT") or "MunsterKickoffBot/1.0"
    )

def already_posted_url(url):
    if not os.path.exists(MATCH_HISTORY_FILE):
        return False
    try:
        with open(MATCH_HISTORY_FILE) as f:
            data = json.load(f)
        return url in data
    except Exception:
        return False

def save_posted_url(url):
    data = []
    if os.path.exists(MATCH_HISTORY_FILE):
        try:
            with open(MATCH_HISTORY_FILE) as f:
                data = json.load(f)
        except Exception:
            data = []
    data.append(url)
    with open(MATCH_HISTORY_FILE, "w") as f:
        json.dump(data, f)

def post_match_thread(match):
    reddit = reddit_client()
    subreddit = reddit.subreddit(SUBREDDIT)

    dt_ist = match["datetime"].astimezone(IST)
    title = (
        f"Match Thread: {match['teams']} ({match['competition']}) - "
        f"{dt_ist.strftime('%A %d %b %Y @ %H:%M')} (IST) - {match['venue']}"
    )

    body_lines = []
    body_lines.append(f"🏉 **Kickoff:** {dt_ist.strftime('%A %d %B %Y @ %H:%M (IST)')} - {match['venue']}")
    body_lines.append("")
    body_lines.append(f"🏆 **Competition:** {match['competition']}")
    if match["broadcasters"]:
        body_lines.append("")
        body_lines.append("📺 **Broadcasters:** " + ", ".join(match["broadcasters"]))
    body_lines.append("")
    # Starting XV table (centered)
    home = match["home"]
    away = match["away"]
    home_players = match["lineups"].get(home, [])
    away_players = match["lineups"].get(away, [])
    body_lines.append("🏉 **Starting XV:**")
    body_lines.append("")
    body_lines.append(f"| # | {home} | {away} |")
    body_lines.append(f"|:--:|:--:|:--:|")
    for i in range(15):
        h = home_players[i] if i < len(home_players) else ""
        a = away_players[i] if i < len(away_players) else ""
        # escape pipe characters in names (very rare)
        h = h.replace("|", "\\|")
        a = a.replace("|", "\\|")
        body_lines.append(f"| {i+1} | {h} | {a} |")
    body_lines.append("")
    body_lines.append("**Stand Up And Fight! 💪🔴**")
    body_lines.append("")
    body_lines.append("---")
    body_lines.append("_Automated by /u/MunsterKickoff 🤖_")

    body = "\n".join(body_lines)

    try:
        submission = subreddit.submit(title, selftext=body, flair_id=FLAIR_ID)
        # distinguish + sticky if permitted
        try:
            submission.mod.distinguish(sticky=True)
        except Exception:
            # older praw versions / different perms
            try:
                submission.mod.distinguish()
                submission.mod.sticky()
            except Exception:
                pass
        print(f"✅ Posted: {title}")
        save_posted_url(match["url"])
    except Exception as e:
        print(f"❌ Failed to submit to Reddit: {e}")

# ---------------- main ----------------
def main(force_post=False):
    match_link = find_next_munster_match()
    if not match_link:
        print("No unposted match link found. Exiting.")
        return

    match = scrape_match_and_teams(match_link)
    if not match:
        print("Failed to retrieve match details. Exiting.")
        return

    # Already posted guard (URL)
    if already_posted_url(match["url"]):
        print("Already posted this match. Exiting.")
        return

    now_utc = datetime.now(pytz.utc)
    post_time = match["datetime"] - timedelta(hours=POST_BEFORE_HOURS)
    # If match is live or force_post or now >= post_time -> post
    will_post = force_post or match.get("is_live", False) or (now_utc >= post_time)

    # additional tolerance: if kickoff is very close (within 2 hours) but schedule parsed oddly
    if not will_post:
        if abs((now_utc - match["datetime"]).total_seconds()) < 7200:
            will_post = True

    if will_post:
        print("Posting match thread now...")
        post_match_thread(match)
    else:
        print(f"⏳ Not time yet. Kickoff (UTC): {match['datetime']} | Scheduled post time (UTC): {post_time}")
        return

if __name__ == "__main__":
    # Quick debug: if you want to force a post for testing, set env var FORCE_POST=1 or call script with flag
    import sys
    force = False
    if "--force" in sys.argv or os.getenv("FORCE_POST", "0") == "1":
        force = True
    main(force_post=force)
