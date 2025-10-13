import praw
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import os

WIKI_URL = "https://en.wikipedia.org/wiki/2025–26_Munster_Rugby_season"
SUBREDDIT_NAME = "MunsterRugby"

def get_latest_result():
    """Scrape Wikipedia for Munster’s latest finished match and score."""
    print("🔎 Checking Wikipedia for latest result...")
    res = requests.get(WIKI_URL, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(res.text, "html.parser")

    table = soup.find("table", {"class": "wikitable"})
    if not table:
        print("⚠️ No fixture table found.")
        return None

    rows = table.find_all("tr")
    latest = None

    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cols) < 5:
            continue
        opponent = cols[1]
        result = cols[-2]
        score = cols[-1]

        # Match format like "W 27–20" or "L 10–13"
        if re.search(r"\d+[\u2013-]\d+", score):
            latest = {
                "opponent": opponent,
                "result": result,
                "score": score.replace("–", "-")
            }

    if latest:
        print(f"✅ Found latest result: {latest['score']} vs {latest['opponent']}")
    else:
        print("❌ No final score found yet.")

    return latest

def update_reddit_post(result):
    """Finds and edits the Reddit post to include final score."""
    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("REDDIT_USER_AGENT")
    )

    subreddit = reddit.subreddit(SUBREDDIT_NAME)
    posts = list(subreddit.new(limit=10))

    target_post = None
    for post in posts:
        if "Match Thread" in post.title and result["opponent"].lower() in post.title.lower():
            target_post = post
            break

    if not target_post:
        print("⚠️ No matching match thread found.")
        return

    new_text = f"**_FULL TIME: Munster {result['score']} {result['opponent']} 🏉_**\n\n\n{target_post.selftext}"
    target_post.edit(new_text)
    print(f"✅ Updated Reddit post: {target_post.title}")

if __name__ == "__main__":
    print("🚀 *** Munster Results Updater Started ***")
    result = get_latest_result()
    if result:
        update_reddit_post(result)
    else:
        print("🛑 No result found to update.")
