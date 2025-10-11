import os
import time
import praw
import requests
import json
import urllib.parse

SUBREDDIT = "MunsterRugby"
AUTHOR_TO_MONITOR = "MannyR1022"
CACHE_FILE = "archive_cache.json"


def load_cache():
    """Load cached archive links from JSON file."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache(cache):
    """Save archive link cache to JSON file."""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def get_short_archive_url(url, cache):
    """Submit to archive.ph and return the short link, with retry + caching."""
    if url in cache:
        print(f"🗂️ Cached archive found for: {url}")
        return cache[url]

    encoded = urllib.parse.quote_plus(url)
    fallback = f"https://archive.ph/submit/?url={encoded}"

    for attempt in range(3):
        try:
            print(f"📁 Archiving attempt {attempt + 1}: {url}")
            res = requests.get("https://archive.ph/submit/", params={"url": url}, timeout=25)
            status = res.status_code

            if status in [200, 302]:
                # Case 1: direct redirect to short link
                if res.url.startswith("https://archive.ph/") and "submit" not in res.url:
                    archive_link = res.url
                    print(f"✅ Archive success: {archive_link}")
                    cache[url] = archive_link
                    save_cache(cache)
                    return archive_link

                # Case 2: find short link in HTML
                import re
                match = re.search(r'https://archive\.ph/\w+', res.text)
                if match:
                    archive_link = match.group(0)
                    print(f"✅ Found short archive link: {archive_link}")
                    cache[url] = archive_link
                    save_cache(cache)
                    return archive_link

            if status == 429:
                print("⏳ Rate-limited by archive.ph. Waiting before retry...")
                time.sleep(15 * (attempt + 1))
                continue

            print(f"⚠️ Archive attempt failed: HTTP {status}")

        except Exception as e:
            print(f"❌ Error archiving {url}: {e}")
            time.sleep(10)

    print("⚠️ All attempts failed. Using fallback submit link.")
    cache[url] = fallback
    save_cache(cache)
    return fallback


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

    cache = load_cache()

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

            url = submission.url
            short_link = get_short_archive_url(url, cache)

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

            # avoid hitting Reddit rate limits
            time.sleep(10)


if __name__ == "__main__":
    main()
