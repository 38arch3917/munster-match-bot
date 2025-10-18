import praw
import requests
import time
import os
import logging
from praw.exceptions import APIException

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Reddit client
reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    username=os.getenv("REDDIT_USERNAME"),
    password=os.getenv("REDDIT_PASSWORD"),
    user_agent=os.getenv("USER_AGENT", "Munster Archive Bot v2.2"),
)

# Config
SUBREDDIT_NAME = os.getenv("SUBREDDIT_NAME", "MunsterRugby")
LAST_PROCESSED_FILE = "/tmp/last_processed.txt"
TARGET_DOMAINS = ["independent.ie", "m.independent.ie"]

def get_last_processed_id():
    """Retrieve last processed post ID."""
    try:
        with open(LAST_PROCESSED_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

def set_last_processed_id(submission_id):
    """Save last processed post ID."""
    with open(LAST_PROCESSED_FILE, "w") as f:
        f.write(submission_id)

def already_commented(submission):
    """Check if bot already commented on this post."""
    submission.comments.replace_more(limit=None)
    for comment in submission.comments.list():
        if not comment.author:
            continue
        body = (comment.body or "").lower()
        if str(comment.author).lower() == reddit.user.me().name.lower() or "<!--archivebot-->" in body:
            return True
    return False

def submit_archive(url):
    """Submit article to archive.ph and return the final archived link."""
    submit_url = f"https://archive.ph/submit/?url={url}"
    try:
        response = requests.get(submit_url, timeout=20, allow_redirects=True)
        if response.status_code == 429:
            logger.warning("⚠️ Archive submission failed: 429 (Rate Limited)")
            return None
        if response.status_code == 200 and "archive.ph" in response.url:
            return response.url
    except Exception as e:
        logger.error(f"⚠️ Error submitting to archive.ph: {e}")
    return None

def process_new_posts():
    """Monitor subreddit and comment on new Independent.ie articles."""
    logger.info(f"🚀 *** Archive Bot started for r/{SUBREDDIT_NAME}")
    logger.info(f"✅ Logged in as: {reddit.user.me().name}")
    logger.info(f"👀 Monitoring subreddit: {SUBREDDIT_NAME}")

    subreddit = reddit.subreddit(SUBREDDIT_NAME)
    last_processed = get_last_processed_id()

    while True:
        try:
            for submission in subreddit.new(limit=25):
                # Stop once we reach the last processed post
                if last_processed and submission.id == last_processed:
                    logger.info("🛑 Reached last processed post. Exiting.")
                    set_last_processed_id(last_processed)
                    return

                # Skip if already processed
                if already_commented(submission):
                    logger.info("⚙️ Already commented on this post. Skipping.")
                    continue

                # Check for valid domain
                if not submission.url or not any(domain in submission.url for domain in TARGET_DOMAINS):
                    continue

                logger.info(f"🧾 Found article: {submission.title}")
                logger.info(f"📁 Archiving: {submission.url}")

                archive_link = submit_archive(submission.url)

                # Fallback link if archive fails or rate-limited
                if not archive_link:
                    archive_link = f"https://archive.ph/submit/?url={submission.url}"
                    logger.warning("⚠️ Using fallback archive.ph submit link.")

                # Comment body
                comment_text = (
                    f"🔥🔗 [Archive link for this article]({archive_link})\n"
                    f"---\n"
                    f"_This comment has been automated_\n"
                )

                # Post comment
                comment = submission.reply(comment_text)
                logger.info(f"✅ Commented on: {submission.title}")

                # Try to sticky & distinguish the comment
                try:
                    comment.mod.distinguish(sticky=True)
                    logger.info("📌 Comment distinguished and stickied successfully.")
                except APIException as e:
                    logger.warning(f"⚠️ Failed to sticky comment: {e}")
                except Exception as e:
                    logger.warning(f"⚠️ Unexpected error when stickying: {e}")

                # Save last processed post ID
                last_processed = submission.id
                set_last_processed_id(last_processed)

                time.sleep(20)  # Reddit rate limit buffer

            logger.info("🕵️ No new target posts found.")
            if os.getenv("RUN_ONCE"):
                set_last_processed_id(last_processed or "")
                break
            time.sleep(120)  # Wait before next scan

        except Exception as e:
            logger.error(f"⚠️ Error in main loop: {e}")
            time.sleep(60)

if __name__ == "__main__":
    process_new_posts()
