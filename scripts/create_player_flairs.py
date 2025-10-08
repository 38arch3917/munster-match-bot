import praw
import requests
from bs4 import BeautifulSoup
import os
import json

# ---------- CONFIG ----------
SUBREDDIT = "Munsterrugby"
SQUAD_URL = "https://www.munsterrugby.ie/teams/munster-squad/"
OUTPUT_FILE = "munster_flairs.json"
# ----------------------------

# Reddit authentication
reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    username=os.getenv("REDDIT_USERNAME"),
    password=os.getenv("REDDIT_PASSWORD"),
    user_agent=os.getenv("USER_AGENT")
)

def fetch_players():
    """Scrape player names and headshot URLs from Munster Rugby site"""
    print("Fetching Munster squad list...")
    r = requests.get(SQUAD_URL)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    players = []

    for p in soup.select(".player-item"):
        name = p.get_text(strip=True)
        img_tag = p.find("img")
        if name and img_tag and img_tag.get("src"):
            img_url = img_tag["src"]
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            players.append({"name": name, "img": img_url})

    print(f"✅ Found {len(players)} players.")
    return players

def create_flairs(players):
    """Create text-only flairs for each player in the subreddit"""
    subreddit = reddit.subreddit(SUBREDDIT)
    existing = list(subreddit.flair.templates)
    existing_names = [f["text"] for f in existing if f["text"]]

    for player in players:
        if player["name"] not in existing_names:
            print(f"Adding flair: {player['name']}")
            subreddit.flair.templates.add(
                text=player["name"],
                css_class="",
                text_editable=False
            )
        else:
            print(f"Already exists: {player['name']}")

    # Save output to file for later reference
    with open(OUTPUT_FILE, "w") as f:
        json.dump(players, f, indent=2)
    print(f"💾 Saved player data to {OUTPUT_FILE}")

if __name__ == "__main__":
    players = fetch_players()
    create_flairs(players)
