#!/usr/bin/env python3
"""
munster_bot.py — updated with sanity checking and preview mode
"""

import os
import re
import json
import sys
import time
import pytz
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
POST_BEFORE_HOURS = 3
POSTED_FILE = "posted.json"
IST = pytz.timezone("Europe/Dublin")
HEADERS = {"User-Agent": os.getenv("USER_AGENT", "MunsterKickoffBot/1.0 (by /u/MunsterKickoff)")}
STANDINGS_KEYWORDS = ["United Rugby Championship", "URC", "Champions Cup", "Challenge Cup"]


def safe_get(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=20, headers=HEADERS)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"HTTP error {e} for {url}")
        return None


def load_posted():
    if not os.path.exists(POSTED_FILE):
        return []
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_posted(lst):
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(lst, f, indent=2)


def search_titles(query):
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 6,
        "format": "json"
    }
    r = safe_get("https://en.wikipedia.org/w/api.php", params)
    if not r:
        return []
    try:
        data = r.json()
        return [s["title"] for s in data.get("query", {}).get("search", [])]
    except Exception:
        return []


def wiki_html(title):
    r = safe_get("https://en.wikipedia.org/wiki/" + title.replace(" ", "_"))
    return r.text if r else None


def infer_queries():
    now = datetime.now()
    y = now.year
    return [
        f"Munster_Rugby_{y}–{str(y+1)[-2:]}_season",
        f"Munster_Rugby_{y-1}–{str(y)[-2:]}_season",
        "Munster_Rugby_fixtures",
        "Munster_Rugby_season"
    ]


def parse_datetime_text(s):
    if not s:
        return None
    s = s.strip()
    # try dateutil
    try:
        dt = dateparser.parse(s, dayfirst=True)
        if dt and dt.tzinfo is None:
            dt = IST.localize(dt)
        if dt:
            return dt.astimezone(pytz.utc)
    except Exception:
        pass
    # fallback formats
    fmts = ["%d %B %Y %H:%M", "%d %b %Y %H:%M", "%A %d %B %Y %H:%M", "%d %B %Y"]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            dt = IST.localize(dt)
            return dt.astimezone(pytz.utc)
        except Exception:
            continue
    # partial parse
    m = re.search(r'(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}).*?(\d{1,2}:\d{2})', s)
    if m:
        try:
            dt = dateparser.parse(m.group(1) + " " + m.group(2), dayfirst=True)
            if dt and dt.tzinfo is None:
                dt = IST.localize(dt)
            return dt.astimezone(pytz.utc)
        except Exception:
            pass
    return None


def extract_fixtures(html):
    soup = BeautifulSoup(html, "html.parser")
    fixtures = []
    for t in soup.select("table.wikitable"):
        for tr in t.select("tr")[1:]:
            cols = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if not cols:
                continue
            txt = " ".join(cols)
            if TEAM_NAME.lower() not in txt.lower():
                continue
            # heuristics
            date_txt = ""
            opponent = ""
            comp = ""
            venue = ""
            for c in cols:
                if re.search(r'\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', c, re.I):
                    date_txt = c
                if re.search(r'\d{1,2}:\d{2}', c) and date_txt:
                    date_txt = date_txt + " " + c
                if re.search(r'\b(vs|v\.|v|versus)\b', c, re.I) or re.search(r'\b(Leinster|Ulster|Edinburgh|Glasgow|Cardiff|Bulls|Benetton)\b', c, re.I):
                    opponent = c
                if re.search(r'\b(United Rugby Championship|URC|Champions Cup|Challenge Cup)\b', c, re.I):
                    comp = c
                if re.search(r'\b(Stadium|Park|Ground|Arena|Thomond|Aviva)\b', c, re.I):
                    venue = c
            if not opponent and len(cols) >= 2:
                opponent = cols[1]
            if not date_txt and len(cols) >= 1:
                date_txt = cols[0]
            dt = parse_datetime_text(date_txt)
            # normalize opponent part
            away = opponent
            parts = re.split(r'–|-|—|\bvs?\.?\b|\bversus\b', opponent, flags=re.I)
            if len(parts) >= 2:
                if TEAM_NAME.lower() in parts[0].lower():
                    away = parts[1].strip()
                else:
                    away = parts[0].strip()
            fixtures.append({
                "datetime": dt,
                "date_text": date_txt,
                "away": away,
                "competition": comp,
                "venue": venue,
                "source_page": None
            })
    return fixtures


def discover_fixtures():
    cand = []
    for q in infer_queries():
        for title in search_titles(q):
            html = wiki_html(title)
            if not html:
                continue
            fx = extract_fixtures(html)
            for f in fx:
                f["source_page"] = title
                cand.append(f)
            time.sleep(0.3)
    html = wiki_html("Munster_Rugby")
    if html:
        for f in extract_fixtures(html):
            f["source_page"] = "Munster_Rugby"
            cand.append(f)
    # dedupe
    uniq = {}
    for f in cand:
        key = (f.get("away","").lower(), f.get("date_text",""))
        if key not in uniq:
            uniq[key] = f
    fixtures = list(uniq.values())
    # filter
    now = datetime.now(pytz.utc)
    out = []
    for f in fixtures:
        dt = f.get("datetime")
        if dt:
            if dt >= now - timedelta(days=1):
                out.append(f)
        else:
            if f.get("date_text"):
                out.append(f)
    out.sort(key=lambda x: x["datetime"] or datetime.max.replace(tzinfo=pytz.utc))
    return out


def pick_next(fixtures):
    now = datetime.now(pytz.utc)
    for f in fixtures:
        dt = f.get("datetime")
        if dt and dt > now - timedelta(hours=1):
            return f
    return fixtures[0] if fixtures else None


def sanity_check_fixture(f):
    now = datetime.now(pytz.utc)
    dt = f.get("datetime")
    away = (f.get("away") or "").strip()
    venue = (f.get("venue") or "").strip()

    if dt is None:
        return False, "Missing parsed datetime"
    if dt.tzinfo is None:
        return False, "Datetime has no timezone"
    if dt < now - timedelta(hours=1):
        return False, "Kickoff is in the past"
    if abs((dt - now).total_seconds()) < 30:
        return False, "Parsed kickoff equals now"
    if dt > now + timedelta(days=365):
        return False, "Kickoff too far in future"
    if not away or away.lower() in ("tbc", "munster", "opponent", ""):
        return False, "Invalid opponent parsed"
    # venue optional
    return True, "OK"


def format_title(f):
    away = f.get("away") or "Opponent"
    comp = f.get("competition") or "Fixture"
    venue = f.get("venue") or "TBC"
    dt = f.get("datetime")
    if dt:
        dt_ist = dt.astimezone(IST)
        datepart = dt_ist.strftime("%a %d %b %Y @ %H:%Mhrs (IST)")
    else:
        datepart = "TBC"
    return f"Match Thread: {TEAM_NAME} vs. {away} ({comp}) - {datepart} - {venue}"


def format_body(f):
    lines = []
    dt = f.get("datetime")
    if dt:
        dt_ist = dt.astimezone(IST)
        kickoff = dt_ist.strftime("%A %d %B %Y @ %H:%M (IST)")
    else:
        kickoff = f.get("date_text") or "TBC"
    lines.append(f"🏉 **Kickoff:** {kickoff} - {f.get('venue','TBC')}")
    lines.append("")
    lines.append(f"🏆 **Competition:** {f.get('competition') or 'Fixture'}")
    lines.append("")
    lines.append("**Stand Up And Fight! 💪🔴**")
    lines.append("")
    lines.append("---")
    lines.append("_Automated by /u/MunsterKickoff 🤖_")
    return "\n".join(lines)


def reddit_client():
    import praw
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT", "MunsterKickoffBot/1.0 (by /u/MunsterKickoff)")
    )


def post_thread(f, debug=False, force=False):
    key = f"{f.get('away')}|{f.get('date_text')}"
    posted = load_posted()
    if key in posted and not force:
        print("Already posted this fixture; skipping.")
        return
    ok, reason = sanity_check_fixture(f)
    print("Sanity check:", ok, "| reason:", reason)
    if not ok:
        print("Will not post fixture due to failed sanity check.")
        return
    title = format_title(f)
    body = format_body(f)
    print("\n=== Thread Preview ===")
    print(title)
    print(body)
    print("======================")
    if debug:
        print("Debug mode: not posting.")
        return
    reddit = reddit_client()
    sr = reddit.subreddit(SUBREDDIT)
    sub = sr.submit(title, selftext=body)
    try:
        sub.mod.distinguish(sticky=True)
    except Exception:
        pass
    posted.append(key)
    save_posted(posted)
    print("Posted:", sub.id)


def main(force=False, debug=False):
    fixtures = discover_fixtures()
    if not fixtures:
        print("No fixtures discovered.")
        return
    nextf = pick_next(fixtures)
    if not nextf:
        print("No next fixture found.")
        return
    dt = nextf.get("datetime")
    now = datetime.now(pytz.utc)
    post_time = dt - timedelta(hours=POST_BEFORE_HOURS) if dt else None
    print("Next fixture:", nextf.get("away"), nextf.get("date_text"), nextf.get("competition"))
    print("Kickoff (UTC):", dt, "| Post time (UTC):", post_time)
    if force or (dt and now >= post_time):
        post_thread(nextf, debug=debug, force=force)
    else:
        print("Too early to post; waiting.")


if __name__ == "__main__":
    force = "--force" in sys.argv
    debug = "--debug" in sys.argv
    main(force=force, debug=debug)
