#!/usr/bin/env python3
"""
munster_bot.py
Wikipedia-based Munster Rugby match-thread bot
Posts automatically 3 hours before kickoff.
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
HEADERS = {"User-Agent": "MunsterKickoffBot/1.0 (by /u/MunsterKickoff)"}
STANDINGS_KEYWORDS = ["United Rugby Championship", "URC", "Champions Cup", "Challenge Cup"]

def safe_get(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=20, headers=HEADERS)
        r.raise_for_status()
        return r
    except Exception as e:
        print("Error:", e)
        return None

def load_posted():
    if not os.path.exists(POSTED_FILE):
        return []
    try:
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_posted(data):
    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def wiki_html(title):
    r = safe_get("https://en.wikipedia.org/wiki/" + title.replace(" ", "_"))
    return r.text if r else None

def search_titles(query):
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 6,
        "format": "json"
    }
    r = safe_get("https://en.wikipedia.org/w/api.php", params)
    if not r: return []
    data = r.json()
    return [s["title"] for s in data.get("query", {}).get("search", [])]

def infer_queries():
    y = datetime.now().year
    return [
        f"Munster_Rugby_{y}–{str(y+1)[-2:]}_season",
        f"Munster_Rugby_{y-1}–{str(y)[-2:]}_season",
        "Munster_Rugby_fixtures"
    ]

def parse_date(s):
    if not s: return None
    try:
        dt = dateparser.parse(s, dayfirst=True)
        if dt and dt.tzinfo is None:
            dt = IST.localize(dt)
        return dt.astimezone(pytz.utc)
    except Exception:
        return None

def extract_fixtures(html):
    soup = BeautifulSoup(html, "html.parser")
    fixtures = []
    for t in soup.select("table.wikitable"):
        for tr in t.select("tr")[1:]:
            cols = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if not cols: continue
            txt = " ".join(cols)
            if TEAM_NAME.lower() not in txt.lower():
                continue
            date_txt = next((c for c in cols if re.search(r"\d", c)), "")
            dt = parse_date(date_txt)
            opponent = ""
            for c in cols:
                if "v" in c.lower() and TEAM_NAME.lower() in c.lower():
                    parts = re.split(r"v|vs|–|-|—", c)
                    for p in parts:
                        if TEAM_NAME.lower() not in p.lower():
                            opponent = p.strip()
                            break
            comp = next((c for c in cols if "Champ" in c or "URC" in c or "League" in c), "")
            venue = next((c for c in cols if "Park" in c or "Ground" in c or "Stadium" in c), "")
            fixtures.append({
                "datetime": dt,
                "away": opponent,
                "competition": comp,
                "venue": venue,
                "date_text": date_txt,
                "source_page": "Munster"
            })
    return fixtures

def discover_fixtures():
    results = []
    for q in infer_queries():
        for title in search_titles(q):
            html = wiki_html(title)
            if not html: continue
            fx = extract_fixtures(html)
            for f in fx:
                f["source_page"] = title
                results.append(f)
            time.sleep(0.3)
    html = wiki_html("Munster_Rugby")
    if html:
        results += extract_fixtures(html)
    seen = {}
    for f in results:
        key = (f.get("away",""), f.get("date_text",""))
        seen[key] = f
    future = []
    now = datetime.now(pytz.utc)
    for f in seen.values():
        dt = f.get("datetime")
        if not dt or dt > now - timedelta(days=1):
            future.append(f)
    future.sort(key=lambda x: x.get("datetime") or datetime.max.replace(tzinfo=pytz.utc))
    return future

def pick_next(fixtures):
    now = datetime.now(pytz.utc)
    for f in fixtures:
        dt = f.get("datetime")
        if dt and dt > now - timedelta(hours=1):
            return f
    return fixtures[0] if fixtures else None

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
        print("Already posted this fixture.")
        return
    title = format_title(f)
    body = format_body(f)
    print("\n=== Preview ===")
    print(title)
    print(body)
    print("===============")
    if debug:
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
        print("No fixtures found.")
        return
    nextf = pick_next(fixtures)
    if not nextf:
        print("No next fixture.")
        return
    dt = nextf.get("datetime")
    now = datetime.now(pytz.utc)
    if not dt or force or now >= dt - timedelta(hours=POST_BEFORE_HOURS):
        post_thread(nextf, debug=debug, force=force)
    else:
        print("Too early to post yet.")

if __name__ == "__main__":
    force = "--force" in sys.argv
    debug = "--debug" in sys.argv
    main(force=force, debug=debug)
