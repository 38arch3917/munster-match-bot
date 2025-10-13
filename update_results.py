#!/usr/bin/env python3
"""
update_results.py
Adds FULL TIME line to the latest posted match threads once scores appear on Wikipedia.
"""

import os
import re
import pytz
import requests
import json
from bs4 import BeautifulSoup

TEAM = "Munster"
POSTED_FILE = "posted.json"
HEADERS = {"User-Agent": "MunsterKickoffBot/1.0 (by /u/MunsterKickoff)"}

def safe_get(url):
    try:
        r = requests.get(url, timeout=15, headers=HEADERS)
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

def reddit_client():
    import praw
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT", "MunsterKickoffBot/1.0 (by /u/MunsterKickoff)")
    )

def find_final_score(page, opponent):
    r = safe_get("https://en.wikipedia.org/wiki/" + page.replace(" ", "_"))
    if not r: return None
    soup = BeautifulSoup(r.text, "html.parser")
    for tr in soup.select("tr"):
        txt = tr.get_text(" ", strip=True)
        if TEAM.lower() in txt.lower() and opponent.lower() in txt.lower():
            m = re.search(r"(\d{1,3})\s*[–-]\s*(\d{1,3})", txt)
            if not m: continue
            a, b = m.groups()
            if txt.lower().find(TEAM.lower()) < txt.lower().find(opponent.lower()):
                return f"**_FULL TIME: Munster {a} - {b} {opponent} 🏉_**"
            else:
                return f"**_FULL TIME: Munster {b} - {a} {opponent} 🏉_**"
    return None

def update_posts():
    posted = load_posted()
    if not posted: 
        print("No posted.json entries.")
        return
    reddit = reddit_client()
    sr = reddit.subreddit("Munsterrugby")
    recent = list(sr.new(limit=30))
    for key in posted:
        parts = key.split("|")
        if len(parts) < 2: continue
        opponent = parts[0].strip()
        date_text = parts[1].strip()
        match_post = None
        for p in recent:
            if TEAM.lower() in p.title.lower() and opponent.lower() in p.title.lower():
                match_post = p
                break
        if not match_post:
            continue
        page = "Munster_Rugby"
        score_md = find_final_score(page, opponent)
        if not score_md:
            continue
        if "FULL TIME:" in (match_post.selftext or ""):
            continue
        new_body = score_md + "\n\n\n" + match_post.selftext
        try:
            match_post.edit(new_body)
            print(f"✅ Updated {p.title}")
        except Exception as e:
            print("❌ Edit failed:", e)

if __name__ == "__main__":
    update_posts()
