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

SUBREDDIT_NAME = os.getenv("SUBREDDIT_NAME", "MunsterRugby")
TARGET_USER = os.getenv("TARGET_USER", "MannyR1022")
TARGET_DOMAIN = os.getenv("TARGET_DOMAIN", "independent.ie")
LAST_PROCESSED_FILE = "/tmp/last_processed.txt"  # Temp file for persistence (Actions resets, but helps across runs if needed)

def get_last_processed_id():
    """Get ID of last processed post to skip old ones."""
    try:
        with open(LAST_PROCESSED_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

def set_last_processed_id(submission_id):
    """Save ID of latest processed post."""
    with open(LAST_PROCESSED_FILE, "w") as f:
        f.write(submission_id)

def already_commented(submission):
    """Check if the bot has already commented on this post."""
    submission.comments.replace_more(limit=None)
    for comment in submission.comments.list():
        body = (comment.body or "").lower()
        if str(comment.author).lower() == reddit.user.me().name.lower() or "<!--archivebot-->" in body:
            return True
    return False

def submit_archive(url):
    """Try to submit the article to archive.ph via GET and return a usable link."""
    submit_url = f"https://archive.ph/submit/?url={url}"
    try:
        # Use GET: Triggers archiving and redirects to result
        response = requests.get(submit_url, timeout=20, allow_redirects=True)
        if response.status_code == 429:
            logger.warning("⚠️ Archive submission failed: 429 (Rate Limited)")
            return None
        if response.status_code == 200 and "archive.ph" in response.url:
            # Redirected to archived page
            return response.url
    except Exception as e:
        logger.error(f"⚠️ Error submitting to archive.ph: {e}")
    return None

def process_new_posts():
    """Monitor subreddit and comment archive links on new posts."""
    logger.info(f"🚀 *** Archive Bot started for r/{SUBREDDIT_NAME}")
    logger.info(f"✅ Logged in as: {reddit.user.me().name}")
    logger.info(f"👀 Monitoring subreddit: {SUBREDDIT_NAME}")

    subreddit = reddit.subreddit(SUBREDDIT_NAME)
    last_processed = get_last_processed_id()

    while True:  # Single pass per Action run; loop for local testing
        try:
            for submission in subreddit.new(limit=25):  # Increased to 25 for safety
                # Skip if older than last processed (sort by new, so break early)
                if last_processed and submission.id == last_processed:
                    logger.info("🛑 Reached last processed post. Exiting.")
                    set_last_processed_id(last_processed)  # Persist
                    return

                # Only target posts by specific user
                if str(submission.author).lower() != TARGET_USER.lower():
                    continue

                logger.info(f"🧾 Found post by {submission.author}: {submission.title}")

                if already_commented(submission):
                    logger.info("⚙️ Already commented on this post. Skipping.")
                    continue

                # Find a link in the post
                if not submission.url or TARGET_DOMAIN not in submission.url:
                    logger.warning("⚠️ No valid target link found. Skipping.")
                    continue

                logger.info(f"📁 Archiving: {submission.url}")
                archive_link = submit_archive(submission.url)

                # If archive fails, still provide fallback
                if not archive_link:
                    archive_link = f"https://archive.ph/submit/?url={submission.url}"
                    logger.warning("⚠️ Using fallback archive.ph submit link.")

                comment_text = (
                    f"🔥🔗 [Archive link for this article]({archive_link})\n"
                    f"---\n"
                    f"_Automated by /u/MunsterKickoff 🤖_\n\n"
                    f"<!--archivebot-->"
                )

                submission.reply(comment_text)
                logger.info(f"✅ Commented on post: {submission.title}")
                last_processed = submission.id  # Update for next iteration
                time.sleep(20)  # Rate limit sleep

            logger.info("🕵️ No new target posts found or from another user.")
            if os.getenv("RUN_ONCE"):  # For Actions: Exit after one pass
                set_last_processed_id(last_processed or "")
                break
            time.sleep(120)  # Check every 2 minutes (local only)

        except Exception as e:
            logger.error(f"⚠️ Error in main loop: {e}")
            time.sleep(60)

if __name__ == "__main__":
    process_new_posts()
