import praw
import time
import json
import requests
from datetime import datetime

# Constants
SUBREDDIT_NAME = "MunsterRugby"
BOT_USERNAME = "MunsterKickoff"
TARGET_USER = "MannyR1022"
POSTED_FILE = "posted_archives.json"

# Load Reddit credentials from secrets/environment variables
import os

reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    username=os.getenv("REDDIT_USERNAME"),
    password=os.getenv("REDDIT_PASSWORD"),
    user_agent=os.getenv("USER_AGENT", "MunsterKickoff Bot v1.0")
)


def get_archive_url(url):
    """Generate archive.ph link."""
    try:
        archive_req = requests.post("https://archive.ph/submit/", data={"url": url}, timeout=20)
        if archive_req.ok:
            return archive_req.url
    except Exception as e:
        print(f"Error archiving {url}: {e}")
    return f"https://archive.ph/?run=1&url={url}"


def has_existing_comment(submission, reddit):
    """Check if MunsterKickoff already commented and re-sticky if needed."""
    submission.comments.replace_more(limit=0)
    for comment in submission.comments.list():
        if comment.author and comment.author.name.lower() == BOT_USERNAME.lower():
            try:
                if not comment.stickied:
                    comment.mod.distinguish(sticky=True)
                    print(f"Re-stickied existing comment on: {submission.title}")
            except Exception as e:
                print(f"Error restickying comment: {e}")
            return True
    return False


def load_posted():
    """Load list of already processed submission IDs."""
    if not os.path.exists(POSTED_FILE):
        return []
    with open(POSTED_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_posted(posted):
    """Save updated list of processed submission IDs."""
    with open(POSTED_FILE, "w") as f:
        json.dump(posted, f)


def main():
    subreddit = reddit.subreddit(SUBREDDIT_NAME)
    posted = load_posted()
    new_posted = []

    print(f"Checking subreddit: {SUBREDDIT_NAME} at {datetime.utcnow()} UTC")

    for submission in subreddit.new(limit=10):  # last few new posts
        if submission.id in posted:
            new_posted.append(submission.id)
            continue

        author = submission.author.name if submission.author else "[deleted]"
        if author.lower() != TARGET_USER.lower():
            continue

        if has_existing_comment(submission, reddit):
            new_posted.append(submission.id)
            continue

        archive_url = get_archive_url(submission.url)
        comment_body = (
            f"🔗 **Archived version:** {archive_url}\n\n"
            f"---\n\n"
            f"_Automated by /u/MunsterKickoff 🤖_"
        )

        try:
            comment = submission.reply(comment_body)
            comment.mod.distinguish(sticky=True)
            print(f"✅ Commented and stickied on: {submission.title}")
            new_posted.append(submission.id)
        except Exception as e:
            print(f"Error commenting on {submission.title}: {e}")

        time.sleep(5)

    save_posted(new_posted)


if __name__ == "__main__":
    main()
