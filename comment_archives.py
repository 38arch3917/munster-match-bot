import praw
import requests
import time
import json
from praw.models import Submission

# ==== CONFIGURATION ====
SUBREDDIT = "MunsterRugby"
POSTER_USERNAME = "MannyR1022"
POSTED_FILE = "archived_posts.json"

# Reddit credentials from GitHub secrets
REDDIT_CLIENT_ID = "YOUR_CLIENT_ID"
REDDIT_CLIENT_SECRET = "YOUR_CLIENT_SECRET"
REDDIT_USERNAME = "MunsterKickoff"
REDDIT_PASSWORD = "YOUR_PASSWORD"
USER_AGENT = "MunsterKickoff Bot by u/MunsterKickoff"

# ==== SETUP ====
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    username=REDDIT_USERNAME,
    password=REDDIT_PASSWORD,
    user_agent=USER_AGENT,
)

# ==== UTILITIES ====
def load_posted():
    try:
        with open(POSTED_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_posted(posted):
    with open(POSTED_FILE, "w") as f:
        json.dump(posted, f)

def get_archive_link(url):
    """
    Requests archive.ph to generate or retrieve a short URL for the given article.
    """
    try:
        # Request archive.ph to create the archive
        submit_res = requests.post("https://archive.ph/submit/", data={"url": url}, timeout=30)
        if submit_res.status_code == 200:
            # Try to extract the short link from the returned page
            # archive.ph responds with a redirect or meta refresh URL
            if "archive.ph/" in submit_res.url and "submit" not in submit_res.url:
                return submit_res.url
            # Sometimes it’s in the HTML itself
            import re
            match = re.search(r'https://archive\.ph/[A-Za-z0-9]+', submit_res.text)
            if match:
                return match.group(0)
        print(f"⚠️ Could not get short link, fallback to submit URL.")
        return f"https://archive.ph/submit/?url={url}"
    except Exception as e:
        print(f"❌ Archive.ph error: {e}")
        return f"https://archive.ph/submit/?url={url}"

# ==== MAIN LOGIC ====
def process_new_posts():
    posted = load_posted()
    subreddit = reddit.subreddit(SUBREDDIT)

    print(f"🚀 MunsterKickoff Archive Bot started for r/{SUBREDDIT}")
    print(f"Checking latest posts...")

    for submission in subreddit.new(limit=10):
        author = str(submission.author).lower() if submission.author else ""
        if author == POSTER_USERNAME.lower() and "independent.ie" in submission.url:
            if submission.id not in posted:
                print(f"🆕 Found new Independent.ie post: {submission.title}")

                archive_link = get_archive_link(submission.url)

                comment_body = (
                    f"🔗 **Archived version:** {archive_link}\n\n"
                    "---\n"
                    "_Automated by /u/MunsterKickoff 🤖_"
                )

                try:
                    comment = submission.reply(comment_body)
                    comment.mod.distinguish(sticky=True)
                    print(f"✅ Commented and stickied on: {submission.title}")
                    posted.append(submission.id)
                    save_posted(posted)
                    time.sleep(5)
                except Exception as e:
                    print(f"❌ Failed to comment: {e}")
            else:
                print(f"⏭️ Already processed: {submission.title}")

    print("✅ Done checking new posts.")

if __name__ == "__main__":
    process_new_posts()
