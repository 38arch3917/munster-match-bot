import praw
import os

def main():
    print("🚀 Testing Reddit login credentials...")

    try:
        reddit = praw.Reddit(
            client_id=os.getenv("REDDIT_CLIENT_ID"),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
            username=os.getenv("REDDIT_USERNAME"),
            password=os.getenv("REDDIT_PASSWORD"),
            user_agent=os.getenv("USER_AGENT"),
        )

        me = reddit.user.me()
        if me:
            print(f"✅ Successfully logged in as: {me.name}")
        else:
            print("⚠️ Login succeeded but user.me() returned None — check scopes or app type.")
    except Exception as e:
        print(f"❌ Login failed: {e}")

if __name__ == "__main__":
    main()
