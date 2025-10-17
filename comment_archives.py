import praw
import requests
import time
import os
import logging

# ===== Logging setup =====
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

# ===== Reddit client setup =====
reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    username=os.getenv("REDDIT_USERNAME"),
    password=os.getenv("REDDIT_PASSWORD"),
    user_agent=os.getenv("USER_AGENT", "Munster Archive Bot v2.1"),
)

# ===== Config =====
SUBREDDIT_NAME = os.getenv("SUBREDDIT_NAME") or "MunsterRugby"
TARGET_USER = os.getenv("TARGET_USER") or "MannyR1022"
TARGET_DOMAIN = os.getenv("TARGET_DOMAIN") or "independent.ie"
LAST_PROCESSED_FILE = "/tmp/last_processed.txt"  # ephemeral persistence between runs

# ===== Helper functions =====
def get_last_processed_id():
    try:
        with open(LAST_PROCESSED_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

def set_last_processed_id(submission_id):
    if submission_id:
        with open(LAST_PROCESSED_FILE, "w") as f:
            f.write(submission_id)

def already_commented(submission):
    submission.comments.replace_more(limit=None)
    for comment in submission.comments.list():
        body = (comment.body or "").lower()
        if str(comment.author).lower() == reddit.user.me().name.lower() or "<!--archivebot-->" in body:
            return True
    return False

def submit_archive(url):
    """Submit to archive.ph; return final or fallback link."""
    submit_url = f"https://archive.ph/submit/?url={url}"
    try:
        response = requests.get(submit_url, timeout=25, allow_redirects=True)
        if response.status_code == 429:
            logger.warning("⚠️ Archive submission failed: 429 (Rate Limited)")
            return None
        if response.status_code == 200 and "archive.ph" in response.url:
            return response.url
    except Exception as e:
        logger.error(f"⚠️ Error submitting to archive.ph: {e}")
    return None

# ===== Core bot =====
def process_new_posts():
    logger.info(f"🚀 *** Archive Bot started for r/{SUBREDDIT_NAME}")
    logger.info(f"✅ Logged in as: {reddit.user.me().name}")
    logger.info(f"👀 Monitoring subreddit: {SUBREDDIT_NAME}")

    subreddit = reddit.subreddit(SUBREDDIT_NAME)
    last_processed = get_last_processed_id()

    for submission in subreddit.new(limit=25):
        try:
            # Skip old
            if last_processed and submission.id == last_processed:
                logger.info("🛑 Reached last processed post.")
                break

            # Target user only
            if str(submission.author).lower() != TARGET_USER.lower():
                continue

            logger.info(f"🧾 Found post by {submission.author}: {submission.title}")

            if already_commented(submission):
                logger.info("⚙️ Already commented. Skipping.")
                continue

            if not submission.url or TARGET_DOMAIN not in submission.url:
                logger.warning("⚠️ No valid link to archive. Skipping.")
                continue

            logger.info(f"📁 Archiving: {submission.url}")
            archive_link = submit_archive(submission.url)

            if not archive_link:
                archive_link = f"https://archive.ph/submit/?url={submission.url}"
                logger.warning("⚠️ Using fallback archive.ph submit link.")

            comment_text = (
                f"🔥🔗 [Archive link for this article]({archive_link})\n"
                f"---\n"
                f"_Automated by /u/MunsterKickoff_\n"
            )

            submission.reply(comment_text)
            logger.info(f"✅ Commented successfully on: {submission.title}")
            set_last_processed_id(submission.id)
            time.sleep(25)  # to respect Reddit rate limits

        except Exception as e:
            logger.error(f"⚠️ Error processing post: {e}")
            time.sleep(60)

    logger.info("🕵️ No new target posts found or all already processed.")

if __name__ == "__main__":
    process_new_posts()
