from datetime import datetime, timedelta
import pytz
import os
import praw

# ---------------- CONFIG ----------------
SUBREDDIT = "Munsterrugby"
FLAIR_ID = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"
IRISH_TZ = pytz.timezone("Europe/Dublin")

# Next match manually added
next_match = {
    "teams": "Edinburgh vs. Munster",
    "competition": "URC",
    "datetime_local": IRISH_TZ.localize(datetime(2025,10,10,19,0)),
    "venue": "Murrayfield Stadium",
    "url": "https://www.rugbykickoff.com/game/edinburgh_munster_2025-10-10/"
}

def reddit_client():
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT")
    )

def post_match_thread(match):
    reddit = reddit_client()
    subreddit = reddit.subreddit(SUBREDDIT)
    formatted_date = match["datetime_local"].strftime("%A %d %b %Y @ %H:%Mhrs (IST) - " + match["venue"])
    title = f"🏉 {match['competition']} | {match['teams']} | {formatted_date}"
    body = (
        f"**Kickoff:** {formatted_date}\n\n"
        f"**Competition:** {match['competition']}\n\n"
        f"**Venue:** {match['venue']}\n\n"
        f"**Starting XV ⚫🔴⚪**\n\n"
        f"(To be confirmed)\n\n"
        f"**Stand Up And Fight! 💪🔴**\n\n"
        f"*Posted automatically by MunsterKickoff Bot 🤖*"
    )
    submission = subreddit.submit(title, selftext=body, flair_id=FLAIR_ID)
    submission.mod.distinguish(sticky=True)
    print(f"✅ Posted: {title}")

# ---------------- MAIN ----------------
if __name__ == "__main__":
    post_match_thread(next_match)
