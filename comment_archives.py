import praw
import requests
import time
from datetime import datetime, timezone

# ---------- Reddit API Setup ----------
REDDIT_CLIENT_ID = "YOUR_CLIENT_ID"
REDDIT_CLIENT_SECRET = "YOUR_CLIENT_SECRET"
REDDIT_USERNAME = "MunsterKickoff"
REDDIT_PASSWORD = "YOUR_PASSWORD"
USER_AGENT = "MunsterKickoff Bot by u/MunsterKickoff"

# ---------- Subreddit & Settings ----------
SUBREDDIT = "MunsterRugby"
SOURCE_USER = "MannyR1022"
CHECK_INTERVAL = 60  # seconds between runs (1 min)
COMMENT_TEXT_TEMPLATE = "📰 [Archived Link]({url})\n\n---\n_Automated by /u/MunsterKickoff 🤖_"

# ---------- Connect to Reddit ----------
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    username=REDDIT_USERNAME,
    password=REDDIT_PASSWORD,
    user_agent=USER_AGENT,
)


# ---------- Archive.ph Short Link Creator ----------
def get_short_archive(url):
    """
    Returns a short archive.ph link (e.g., https://archive.ph/j1bC1)
    """
    try:
        session = requests.Session()
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://archive.ph/",
            "Origin": "https://archive.ph",
        }

        # Submit the URL for archiving
        resp = session.post(
            "https://archive.ph/submit/",
            data={"url": url},
            headers=headers,
            allow_redirects=False,
            timeout=60,
        )

        # 1. Check for 'Refresh' header (typical success redirect)
        refresh = resp.headers.get("Refresh")
        if refresh and "url=" in refresh:
            part = refresh.split("url=", 1)[1].strip()
            if part.startswith("/"):
                return "https://archive.ph" + part
            elif part.startswith("http"):
                return part

        # 2. Check for 'Location' header
        loc = resp.headers.get("Location")
        if loc:
            if loc.startswith("/"):
                return "https://archive.ph" + loc
            elif loc.startswith("http"):
                return loc

        # 3. Follow manually to see final redirected URL
        follow = session.get(
            f"https://archive.ph/submit/?url={url}",
            headers=headers,
            timeout=60,
            allow_redirects=True,
        )
        if "archive.ph" in follow.url and not follow.url.endswith("/submit/"):
            return follow.url

    except Exception as e:
        print(f"⚠️ Archive.ph error for {url}: {e}")

    # fallback — full submit version
    return f"https://archive.ph/submit/?url={url}"


# ---------- Check and Comment ----------
def process_new_posts():
    subreddit = reddit.subreddit(SUBREDDIT)
    for submission in subreddit.new(limit=10):
        # Only act on posts by the target user
        if submission.author and submission.author.name.lower() == SOURCE_USER.lower():
            url = submission.url
            already_commented = any(
                comment.author
                and comment.author.name.lower() == REDDIT_USERNAME.lower()
                for comment in submission.comments
            )
            if already_commented:
                continue

            print(f"🆕 Found new post: {submission.title}")

            # Get short archive link
            short_link = get_short_archive(url)
            comment_body = COMMENT_TEXT_TEMPLATE.format(url=short_link)

            try:
                # Post comment
                comment = submission.reply(comment_body)
                comment.mod.distinguish(sticky=True)
                print(f"✅ Commented and stickied: {short_link}")
            except Exception as e:
                print(f"❌ Error commenting: {e}")


# ---------- Main Loop ----------
if __name__ == "__main__":
    print(f"🚀 MunsterKickoff Archive Bot started at {datetime.now(timezone.utc)}")
    while True:
        process_new_posts()
        time.sleep(CHECK_INTERVAL)
