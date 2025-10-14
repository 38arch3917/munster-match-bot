import os
import praw
import requests
import time

# --- Reddit Setup ---
reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    username=os.getenv("REDDIT_USERNAME"),
    password=os.getenv("REDDIT_PASSWORD"),
    user_agent=os.getenv("USER_AGENT", "Munster Archive Bot by /u/MunsterKickoff")
)

SUBREDDIT = "MunsterRugby"
TARGET_USER = "MannyR1022"  # Only comment on posts by this user

print("🚀 *** Archive Bot started for r/MunsterRugby")
print(f"✅ Logged in as: {reddit.user.me()}")
print(f"👀 Monitoring subreddit: {SUBREDDIT}")

def archive_url(original_url):
    """Try to archive the URL and return the archive.ph short link if possible."""
    try:
        # Step 1: Try archive.ph/submit to generate archive
        print(f"📁 Archiving: {original_url}")
        submit_resp = requests.post("https://archive.ph/submit/", data={"url": original_url}, timeout=30)
        if submit_resp.status_code == 200 and "archive.ph" in submit_resp.text:
            # Try to extract the short link
            import re
            match = re.search(r"https://archive\.ph/[A-Za-z0-9]+", submit_resp.text)
            if match:
                short_url = match.group(0)
                print(f"✅ Archive created: {short_url}")
                return short_url
        elif submit_resp.status_code == 429:
            print("⚠️ Rate limited by archive.ph (429). Using submit fallback link.")
            return f"https://archive.ph/submit/?url={original_url}"
    except Exception as e:
        print(f"⚠️ Error during archive creation: {e}")

    # Fallback to just the submit link
    print("⚠️ Could not create archive, returning submit link.")
    return f"https://archive.ph/submit/?url={original_url}"

def already_commented(submission):
    """Check if the bot has already commented on this post."""
    submission.comments.replace_more(limit=0)
    for comment in submission.comments.list():
        if str(comment.author).lower() == reddit.user.me().lower():
            return True
    return False

def process_new_posts():
    subreddit = reddit.subreddit(SUBREDDIT)
    for submission in subreddit.new(limit=10):
        if submission.author and submission.author.name == TARGET_USER:
            print(f"🧾 Found post by {TARGET_USER}: {submission.title}")
            if already_commented(submission):
                print("⚙️ Already commented on this post. Skipping.")
                continue

            # Extract Independent.ie article link
            if "independent.ie" not in submission.url:
                print("❌ No Independent.ie link found. Skipping.")
                continue

            # Try to archive the article
            archive_link = archive_url(submission.url)
            if not archive_link:
                print("⚠️ No archive link found. Skipping post.")
                continue

            # Prepare comment
            comment_text = (
                f"🔥 Archived: {archive_link}\n\n"
                f"_Automated by /u/MunsterKickoff 🤖_"
            )

            # Encode to UTF-8 to ensure emojis render correctly
            comment_text = comment_text.encode("utf-8", "ignore").decode("utf-8")

            # Post comment
            try:
                comment = submission.reply(comment_text)
                comment.mod.distinguish(sticky=True)
                print(f"✅ Commented and stickied on: {submission.title}")
            except Exception as e:
                print(f"⚠️ Error posting comment: {e}")

        else:
            print("🕵️ No new target posts found or from another user.")

# --- Main loop for Actions run ---
if __name__ == "__main__":
    process_new_posts()
