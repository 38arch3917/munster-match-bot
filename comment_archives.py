import praw
import requests
import time
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🚀 Initialize Reddit client
reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    username=os.getenv("REDDIT_USERNAME"),
    password=os.getenv("REDDIT_PASSWORD"),
    user_agent=os.getenv("USER_AGENT", "Munster Archive Bot v2.0"),
)

# 🔧 Configuration
SUBREDDIT_NAME = os.getenv("SUBREDDIT_NAME") or "MunsterRugby"
TARGET_DOMAINS = ["independent.ie", "m.independent.ie", "the42.ie", "irishtimes.com", "m.irishtimes.com", "otbsports.com", "offtheball.com", "irishexaminer.com", "m.thejournal.ie", "thejournal.ie"]
LAST_PROCESSED_FILE = "/tmp/last_processed.txt"

def get_last_processed_id():
    """Retrieve the last processed submission ID to avoid repeats."""
    try:
        with open(LAST_PROCESSED_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

def set_last_processed_id(submission_id):
    """Store the latest processed submission ID."""
    with open(LAST_PROCESSED_FILE, "w") as f:
        f.write(submission_id)

def already_commented(submission):
    """Check if the bot already commented on this post."""
    submission.comments.replace_more(limit=None)
    for comment in submission.comments.list():
        body = (comment.body or "").lower()
        if str(comment.author).lower() == reddit.user.me().name.lower() or "<!--archivebot-->" in body:
            return True
    return False

def submit_archive(url):
    """Submit a URL to archive.ph and return the archived or fallback link."""
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
    """Main bot loop — monitors subreddit and comments archive links."""
    logger.info(f"🚀 *** Archive Bot started for r/{SUBREDDIT_NAME}")
    logger.info(f"✅ Logged in as: {reddit.user.me().name}")
    logger.info(f"👀 Monitoring subreddit: {SUBREDDIT_NAME}")

    subreddit = reddit.subreddit(SUBREDDIT_NAME)
    last_processed = get_last_processed_id()

    while True:
        try:
            for submission in subreddit.new(limit=25):
                if last_processed and submission.id == last_processed:
                    logger.info("🛑 Reached last processed post. Exiting.")
                    set_last_processed_id(last_processed)
                    return

                # Only process independent.ie links
                if not submission.url or not any(domain in submission.url for domain in TARGET_DOMAINS):
                    continue

                logger.info(f"🧾 Found target post: {submission.title} ({submission.url})")

                if already_commented(submission):
                    logger.info("⚙️ Already commented on this post. Skipping.")
                    continue

                # Try to archive the article
                logger.info(f"📁 Archiving: {submission.url}")
                archive_link = submit_archive(submission.url)

                # If the short version fails, fallback to full submit URL
                if not archive_link:
                    archive_link = f"https://archive.ph/submit/?url={submission.url}"
                    logger.warning("⚠️ Using fallback archive.ph submit link.")

                # Build comment text
                comment_text = (
                    f"🔥🔗 [Archive link for this article]({archive_link})\n"
                    f"---\n"
                )

                # Post the comment
                comment = submission.reply(comment_text)
                logger.info(f"✅ Commented on post: {submission.title}")

                # Try to distinguish and sticky if mod privileges exist
                try:
                    comment.mod.distinguish(sticky=True)
                    logger.info("📌 Comment distinguished and stickied.")
                except Exception:
                    logger.info("ℹ️ No mod permissions to sticky comment.")

                # Record last processed post
                last_processed = submission.id
                time.sleep(20)  # Cooldown to avoid Reddit rate limits

            logger.info("🕵️ No new target posts found.")
            if os.getenv("RUN_ONCE"):
                set_last_processed_id(last_processed or "")
                break
            time.sleep(120)

        except Exception as e:
            logger.error(f"⚠️ Error in main loop: {e}")
            time.sleep(60)

if __name__ == "__main__":
    process_new_posts()
