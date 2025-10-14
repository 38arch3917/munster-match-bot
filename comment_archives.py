import praw
import requests
import time
import os

# 🚀 Initialize Reddit client
reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    username=os.getenv("REDDIT_USERNAME"),
    password=os.getenv("REDDIT_PASSWORD"),
    user_agent=os.getenv("USER_AGENT", "Munster Archive Bot v2.0"),
)

SUBREDDIT_NAME = "MunsterRugby"
TARGET_USER = "MannyR1022"

def already_commented(submission):
    """Check if the bot has already commented on this post."""
    submission.comments.replace_more(limit=None)
    for comment in submission.comments.list():
        body = (comment.body or "").lower()
        if str(comment.author).lower() == reddit.user.me().lower() or "<!--archivebot-->" in body:
            return True
    return False

def submit_archive(url):
    """Try to submit the article to archive.ph and return a usable link."""
    submit_url = f"https://archive.ph/submit/?url={url}"
    try:
        response = requests.post(submit_url, timeout=20)
        # archive.ph may redirect or rate-limit
        if response.status_code == 429:
            print("⚠️ Archive submission failed: 429 (Rate Limited)")
            return None
        if response.status_code in (200, 302):
            return response.url if "archive.ph" in response.url else submit_url
    except Exception as e:
        print(f"⚠️ Error submitting to archive.ph: {e}")
    return None

def process_new_posts():
    """Monitor subreddit and comment archive links on new posts."""
    print(f"🚀 *** Archive Bot started for r/{SUBREDDIT_NAME}")
    print(f"✅ Logged in as: {reddit.user.me()}")
    print(f"👀 Monitoring subreddit: {SUBREDDIT_NAME}")

    subreddit = reddit.subreddit(SUBREDDIT_NAME)

    while True:
        try:
            for submission in subreddit.new(limit=10):
                # Only target posts by specific user
                if str(submission.author).lower() != TARGET_USER.lower():
                    continue

                print(f"🧾 Found post by {submission.author}: {submission.title}")

                if already_commented(submission):
                    print("⚙️ Already commented on this post. Skipping.")
                    continue

                # Find a link in the post
                if not submission.url or "independent.ie" not in submission.url:
                    print("⚠️ No valid target link found. Skipping.")
                    continue

                print(f"📁 Archiving: {submission.url}")
                archive_link = submit_archive(submission.url)

                # If archive fails, still provide fallback
                if not archive_link:
                    archive_link = f"https://archive.ph/submit/?url={submission.url}"
                    print("⚠️ Using fallback archive.ph submit link.")

                comment_text = (
                    f"🔥🔗 [Archive link for this article]({archive_link})\n"
                    f"---\n"
                    f"_Automated by /u/MunsterKickoff 🤖_\n\n"
                    f"<!--archivebot-->"
                )

                submission.reply(comment_text)
                print(f"✅ Commented on post: {submission.title}")
                time.sleep(20)

            print("🕵️ No new target posts found or from another user.")
            time.sleep(120)  # check every 2 minutes

        except Exception as e:
            print(f"⚠️ Error in main loop: {e}")
            time.sleep(60)

if __name__ == "__main__":
    process_new_posts()
