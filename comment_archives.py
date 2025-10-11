import os
import time
import praw
import requests
from urllib.parse import quote

# Reddit API credentials (from GitHub secrets)
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")
USER_AGENT = os.getenv("USER_AGENT", "MunsterKickoffBot/1.0 by u/MunsterKickoff")

# Subreddit & poster to monitor
SUBREDDIT_NAME = "MunsterRugby"
TARGET_USER = "MannyR1022"

# Initialize Reddit instance
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    username=REDDIT_USERNAME,
    password=REDDIT_PASSWORD,
    user_agent=USER_AGENT,
)

def get_archive_link(url):
    """
    Submit the article to archive.ph and return the shortened link.
    Handles 429 rate limits gracefully.
    """
    try:
        submit_url = f"https://archive.ph/submit/?url={quote(url)}"
        print(f"📁 Archiving: {url}")
        response = requests.get(submit_url, timeout=20)
        if response.status_code == 429:
            print("⚠️ Archive submission failed: 429 (Rate Limited)")
            return None
        elif response.status_code != 200:
            print(f"⚠️ Unexpected response: {response.status_code}")
            return None

        # Extract shortened archive link
        if "archive.ph/" in response.url:
            return response.url

        # Fallback — extract link manually from redirect or response text
        for line in response.text.splitlines():
            if "archive.ph" in line and "href" in line:
                potential = line.split('"')[1]
                if potential.startswith("https://archive.ph/") and len(potential) < 40:
                    return potential
        return None
    except Exception as e:
        print(f"⚠️ Error getting archive link: {e}")
        return None

def already_commented(submission):
    """Check if bot already commented on this post."""
    submission.comments.replace_more(limit=0)
    for comment in submission.comments.list():
        if comment.author and comment.author.name.lower() == REDDIT_USERNAME.lower():
            return True
    return False

def process_new_posts():
    """Check latest subreddit posts and comment if needed."""
    print(f"🚀 *** Archive Bot started for r/{SUBREDDIT_NAME}")
    print(f"✅ Logged in as: {REDDIT_USERNAME}")
    print(f"👀 Monitoring subreddit: {SUBREDDIT_NAME}")

    subreddit = reddit.subreddit(SUBREDDIT_NAME)

    for submission in subreddit.new(limit=10):
        if submission.author and submission.author.name == TARGET_USER:
            print(f"🧾 Found post by {TARGET_USER}: {submission.title}")

            if already_commented(submission):
                print("⚙️ Already commented on this post. Skipping.")
                continue

            # Look for independent.ie links
            if "independent.ie" in submission.url:
                archive_link = get_archive_link(submission.url)
                if archive_link:
                    comment_text = (
                        f"🔥 **Archived:** {archive_link}\n\n"
                        f"*Automated by /u/MunsterKickoff 🤖*"
                    )
                    comment = submission.reply(comment_text)
                    comment.mod.distinguish(sticky=True)
                    print(f"✅ Commented and stickied on: {submission.title}")
                else:
                    print("⚠️ No archive link found. Skipping post.")
            else:
                print("🔗 Post not from independent.ie, skipping.")
        else:
            print("🕵️ No new target posts found or from another user.")

if __name__ == "__main__":
    process_new_posts()
