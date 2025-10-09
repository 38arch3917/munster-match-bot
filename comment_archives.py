import praw
import os
import json
import time
import requests

# ---------------- CONFIG ----------------
SUBREDDIT = "Munsterrugby"
TARGET_USER = "MannyR1022"
POSTED_FILE = "archive_commented.json"
CHECK_LIMIT = 10  # check last 10 posts
BOT_USERNAME = "MunsterKickoff"
# ----------------------------------------

def reddit_client():
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT")
    )

def load_posted():
    if not os.path.exists(POSTED_FILE):
        return []
    with open(POSTED_FILE) as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_posted(data):
    with open(POSTED_FILE, "w") as f:
        json.dump(data, f)

def get_archive_link(url):
    try:
        res = requests.get(f"https://archive.ph/submit/?url={url}", timeout=30)
        if res.url.startswith("https://archive.ph/"):
            return res.url
        else:
            # sometimes returns HTML page; fallback to just show archive.ph/URL
            return f"https://archive.ph/{url}"
    except Exception as e:
        print(f"Error archiving {url}: {e}")
        return None

def has_existing_comment(submission):
    """Check if MunsterKickoff has already commented on this post."""
    submission.comments.replace_more(limit=0)
    for comment in submission.comments.list():
        if comment.author and comment.author.name.lower() == BOT_USERNAME.lower():
            print(f"Already commented on: {submission.title}")
            return True
    return False

def main():
    reddit = reddit_client()
    subreddit = reddit.subreddit(SUBREDDIT)
    posted = load_posted()
    new_posted = posted.copy()

    for submission in subreddit.new(limit=CHECK_LIMIT):
        if submission.author is None:
            continue
        if submission.author.name.lower() != TARGET_USER.lower():
            continue
        if "independent.ie" not in submission.url.lower():
            continue
        if submission.id in posted:
            continue
        if has_existing_comment(submission):
            new_posted.append(submission.id)
            continue

        print(f"Found new Independent.ie post: {submission.title}")
        archive = get_archive_link(submission.url)
        if not archive:
            print("Could not create archive link.")
            continue

        comment_body = (
            f"🗞️ **Archived Copy:** [{archive}]({archive})\n\n"
            f"*Automated by /u/MunsterKickoff 🤖*"
        )

        try:
            comment = submission.reply(comment_body)
            comment.mod.distinguish(sticky=True)
            print(f"✅ Commented and stickied on post: {submission.title}")
            new_posted.append(submission.id)
            time.sleep(5)
        except Exception as e:
            print(f"❌ Failed to comment on {submission.title}: {e}")

    save_posted(new_posted)

if __name__ == "__main__":
    main()
