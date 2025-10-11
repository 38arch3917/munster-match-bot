import os
import time
import praw
import requests

SUBREDDIT = "MunsterRugby"
AUTHOR_TO_MONITOR = "MannyR1022"

def get_short_archive_url(url):
    """Submit to archive.ph and return the short link."""
    try:
        print(f"📁 Archiving: {url}")
        submit = requests.get("https://archive.ph/submit/", params={"url": url}, timeout=20)
        if submit.status_code in [200, 302]:
            # Check if we got redirected to a real archive
            if submit.url.startswith("https://archive.ph/") and "submit" not in submit.url:
                print(f"✅ Archive success: {submit.url}")
                return submit.url
            # Try to extract from response text if not redirected
            import re
            match = re.search(r'https://archive\.ph/\w+', submit.text)
            if match:
                print(f"✅ Found short archive: {match.group(0)}")
                return match.group(0)
        print(f"⚠️ Archive submission failed: {submit.status_code}")
        return None
    except Exception as e:
        print(f"❌ Error archiving {url}: {e}")
        return None

def main():
    print("🚀 *** Archive Bot started for r/MunsterRugby")

    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT"),
    )

    try:
        print(f"✅ Logged in as: {reddit.user.me()}")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        exit(1)

    subreddit = reddit.subreddit(SUBREDDIT)
    print(f"👀 Monitoring subreddit: {subreddit.display_name}")

    for submission in subreddit.new(limit=10):
        if submission.author and submission.author.name == AUTHOR_TO_MONITOR:
            print(f"🧾 Found post by {AUTHOR_TO_MONITOR}: {submission.title}")

            # Skip if already commented
            submission.comments.replace_more(limit=0)
            already_done = any(
                c.author and c.author.name == reddit.user.me().name for c in submission.comments
            )
            if already_done:
                print("⚙️ Already commented on this post. Skipping.")
                continue

            # Find the link to archive
            url = submission.url
            short_link = get_short_archive_url(url)
            if not short_link:
                print("⚠️ No archive link found. Skipping post.")
                continue

            comment_body = (
                f"🔗 [Archive link for this article]({short_link})\n\n"
                f"---\n"
                f"_Automated by /u/MunsterKickoff 🤖_"
            )

            try:
                print("💬 Posting comment...")
                comment = submission.reply(comment_body)
                comment.mod.distinguish(sticky=True)
                print("✅ Comment posted and stickied successfully.")
            except Exception as e:
                print(f"❌ Error posting comment: {e}")

            time.sleep(10)  # Safety pause between posts

if __name__ == "__main__":
    main()
