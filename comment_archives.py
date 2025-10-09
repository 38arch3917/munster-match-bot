import praw
import time
import json
import requests
from datetime import datetime
import os

# --- CONFIG ---
SUBREDDIT_NAME = "MunsterRugby"
TARGET_USER = "MannyR1022"
BOT_USERNAME = "MunsterKickoff"
POSTED_FILE = "posted_archives.json"
# ---------------

# Authenticate Reddit API
reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    username=os.getenv("REDDIT_USERNAME"),
    password=os.getenv("REDDIT_PASSWORD"),
    user_agent=os.getenv("USER_AGENT", "MunsterKickoff Bot v1.0")
)


def get_archive_url(url):
    """Generate a short archive.ph link (e.g. https://archive.ph/4FngS)."""
    try:
        session = requests.Session()
        resp = session.post("https://archive.ph/submit/", data={"url": url}, timeout=45, allow_redirects=False)

        # Check for 'Refresh' header first
        refresh = resp.headers.get("Refresh")
        if refresh:
            short_link = refresh.split("url=")[-1]
            if short_link.startswith("http"):
                return short_link.strip()

        # Check for 'Location' header (sometimes used)
        if "Location" in resp.headers:
            return resp.headers["Location"].strip()

        # If still nothing, try a follow-up GET to the submit URL
        follow = session.get("https://archive.ph/submit/", params={"url": url}, timeout=45)
        if follow.url and "archive.ph" in follow.url and not follow.url.endswith("/submit/"):
            return follow.url
    except Exception as e:
        print(f"Error archiving {url}: {e}")

    # Fallback
    return f"https://archive.ph/?run=1&url={url}"


def load_posted():
    """Load IDs of posts already processed."""
    if not os.path.exists(POSTED_FILE):
        return []
    try:
        with open(POSTED_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def save_posted(posted):
    """Save IDs of processed posts."""
    with open(POSTED_FILE, "w") as f:
        json.dump(posted, f)


def main():
    subreddit = reddit.subreddit(SUBREDDIT_NAME)
    posted = load_posted()
    new_posted = posted.copy()

    print(f"Checking subreddit '{SUBREDDIT_NAME}' at {datetime.utcnow()} UTC...")

    for submission in subreddit.new(limit=10):  # Check newest 10 posts
        if submission.id in posted:
            continue

        author = submission.author.name if submission.author else "[deleted]"
        if author.lower() != TARGET_USER.lower():
            continue

        # Skip if bot already commented
        already_commented = any(
            comment.author and comment.author.name.lower() == BOT_USERNAME.lower()
            for comment in submission.comments
        )
        if already_commented:
            print(f"Bot already commented on: {submission.title}")
            new_posted.append(submission.id)
            continue

        # Archive and comment
        archive_url = get_archive_url(submission.url)
        comment_text = (
            f"🔗 **Archived version:** {archive_url}\n\n"
            f"---\n\n"
            f"*Automated by /u/MunsterKickoff 🤖🏉*"
        )

        try:
            comment = submission.reply(comment_text)
            comment.mod.distinguish(sticky=True)
            print(f"✅ Commented and stickied on: {submission.title}")
            new_posted.append(submission.id)
        except Exception as e:
            print(f"❌ Error commenting on {submission.title}: {e}")

        time.sleep(5)  # polite delay

    save_posted(new_posted)
    print("✅ Done.")


if __name__ == "__main__":
    main()
