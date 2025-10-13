import requests
import mwparserfromhell
import praw
from datetime import datetime

# ----------------------------
# CONFIG
# ----------------------------
SEASON_PAGE = "2025-26_Munster_Rugby_season"  # Wikipedia page for the season
REDDIT_CLIENT_ID = "your_client_id"
REDDIT_CLIENT_SECRET = "your_client_secret"
REDDIT_USERNAME = "your_username"
REDDIT_PASSWORD = "your_password"
USER_AGENT = "MunsterKickoffBot/1.0 (by /u/YourRedditUsername)"

# ----------------------------
# FETCH WIKIPEDIA PAGE
# ----------------------------
def get_wikitext(page):
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "format": "json",
        "titles": page
    }
    headers = {
        "User-Agent": USER_AGENT
    }

    res = requests.get(url, params=params, headers=headers)
    res.raise_for_status()
    data = res.json()
    pageid = next(iter(data["query"]["pages"]))
    if "revisions" not in data["query"]["pages"][pageid]:
        raise ValueError("Could not fetch page revisions")
    return data["query"]["pages"][pageid]["revisions"][0]["*"]

# ----------------------------
# PARSE FIXTURES FROM WIKITEXT
# ----------------------------
def parse_fixtures(wikitext):
    wikicode = mwparserfromhell.parse(wikitext)
    fixtures = []

    # Find all rugbybox templates
    for template in wikicode.filter_templates(matches=lambda t: t.name.lower().strip().startswith("rugbybox")):
        fixture = {
            "date": template.get("date").value.strip() if template.has("date") else "",
            "time": template.get("time").value.strip() if template.has("time") else "",
            "home": str(template.get("home").value.strip()) if template.has("home") else "",
            "away": str(template.get("away").value.strip()) if template.has("away") else "",
            "score": template.get("score").value.strip() if template.has("score") else "",
            "stadium": template.get("stadium").value.strip() if template.has("stadium") else "",
        }
        fixtures.append(fixture)

    return fixtures

# ----------------------------
# REDDIT LOGIN
# ----------------------------
def reddit_login():
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        username=REDDIT_USERNAME,
        password=REDDIT_PASSWORD,
        user_agent=USER_AGENT
    )
    return reddit

# ----------------------------
# MAIN
# ----------------------------
def main():
    print("🚀 Munster Bot Starting...")
    wikitext = get_wikitext(SEASON_PAGE)
    fixtures = parse_fixtures(wikitext)

    if not fixtures:
        print("❌ No fixtures found.")
        return

    print(f"✅ Found {len(fixtures)} fixtures.")
    for f in fixtures:
        print(f"{f['date']} | {f['home']} vs {f['away']} | {f['score']} | {f['stadium']}")

    reddit = reddit_login()
    print(f"✅ Logged in as: {reddit.user.me()}")

if __name__ == "__main__":
    main()
