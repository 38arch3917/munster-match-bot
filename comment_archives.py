import praw
import requests
import time
import os
from urllib.parse import quote

# --- Reddit API Setup ---
reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    username=os.getenv("REDDIT_USERNAME"),
    password=os.getenv("REDDIT_PASSWORD"),
    user_agent="MunsterRugbyArchiveBot by /u/MunsterKickoff"
)

SUBREDDIT = "MunsterRugby"
POST_LIMIT = 10
COMMENT_TAG = "🔥 Archived:"

def archive_link(url):
    """
    Attempts to get a short archive.ph link.
    Falls back to full submit link if rate-limited or error occurs.
    """
    try:
        print(f"📁 Archiving: {url}")
        response = requests.post("https://archive.ph/submit/", data={"url": url}, timeout=30)
        if response.status_code == 429:
            print("⚠️ Archive submission failed: 429 (Rate Limited)")
            raise Exception("Rate limited")
        elif response.status_code != 200:
            print(f"⚠️ Archive submission failed: {response.status_code}")
            raise Exception("Archive failed")

        # Extract archive link from response
        if "archive.ph/" in response.url:
            short_link = response.url
            print(f"🔥 Archived: {short_link}")
            return short_link
        else:
            raise Exception("Short link not found")

    except Exception as e:
        # Fallback to full submit link
        fallback_link = f"https://archive.ph/submit/?url={quote(url)}"
        print(f"⚠️ Falling back to submit link: {fallback_link}")
        return fallback_link


def process_new_posts():
    subreddit = reddit.subreddit(SUBREDDIT)
    print(f"👀 Monitoring subreddit: {SUBREDDIT}")

    for submission in subreddit.new(limit=POST_LIMIT):
        if submission.author and submission.author.name.lower() == "munsterkickoff":
            continue  # skip bot's own posts

        # Only process Irish Independent or relevant media posts
        if "independent.ie" in submission.url or "irishexaminer.com" in submission.url:
            print(f"🧾 Found post by {submission.author}: {submission.title}")
            
            # Check if already commented
            submission.comments.replace_more(limit=0)
            if any(COMMENT_TAG in comment.body for comment in submission.comments.list()):
                print("⚙️ Already commented on this post. Skipping.")
                continue

            archive_url = archive_link(submission.url)
            if archive_url:
                comment_text = f"🔥 Archived: {archive_url}\n\n*Automated by /u/MunsterKickoff 🤖*"
                try:
                    submission.reply(comment_text)
                    print(f"💬 Commented successfully on post: {submission.title}")
                    time.sleep(30)
                except Exception as e:
                    print(f"⚠️ Failed to comment: {e}")
            else:
                print("⚠️ No archive link found. Skipping post.")
        else:
            print("🕵️ No new target posts found or from another user.")


if __name__ == "__main__":
    print("🚀 *** Archive Bot started for r/MunsterRugby")
    try:
        process_new_posts()
    except Exception as e:
        print(f"❌ Error running bot: {e}")
