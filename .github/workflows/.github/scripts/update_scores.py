# .github/scripts/update_scores.py
# Called by update-scores.yml

import json
import os
import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo
import praw
import re

MATCH_HISTORY_FILE = "posted.json"
IRELAND_TZ = ZoneInfo("Europe/Dublin")
# helper to load posted entries
def load_posted():
    if not os.path.exists(MATCH_HISTORY_FILE):
        return []
    try:
        with open(MATCH_HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def save_posted(data):
    with open(MATCH_HISTORY_FILE, "w") as f:
        json.dump(data, f, default=str, indent=2)

# best-effort function to fetch final score from rugbykickoff or ESPN
def fetch_final_score_for_entry(entry):
    """
    Try to find final score text like "Munster 24 - 17 Cardiff" and a status like "FT".
    Returns tuple (status_str, score_line) or (None,None)
    """
    # 1) Try rugbykickoff team page (using saved source_url as a hint)
    try:
        url = entry.get("source_url")
        if url:
            r = requests.get(url, timeout=10)
            if r.ok:
                soup = BeautifulSoup(r.text, "html.parser")
                text = soup.get_text(" ", strip=True)
                # Look for 'FT' or 'Full-time' and a score pattern nearby
                ft_match = re.search(r"(Full[-\s]*time|FT|Final)[\s\:\-]*(.*?)(\d{1,3}\s*[-–]\s*\d{1,3})", text, re.I)
                if ft_match:
                    # find the score substring
                    score_search = re.search(r"(\d{1,3}\s*[-–]\s*\d{1,3})", ft_match.group(0))
                    if score_search:
                        score = score_search.group(1).replace("–", "-").strip()
                        # Try to get names from entry
                        teams = entry.get("teams", "")
                        parts = teams.split(" vs ")
                        home = parts[0].strip() if len(parts) >= 2 else "Munster"
                        away = parts[1].strip() if len(parts) >= 2 else "Opponent"
                        # Assemble FT line
                        return ("FT", f"🏉 FT: {home} {score} {away}")
    except Exception:
        pass

    # 2) Try ESPN by searching for team names + "rugby" or checking a known pattern (not always reliable)
    # If you have a mapping from match -> ESPN gameId you should use that. For now we attempt a generic search.
    # Quick attempt: search ESPN match pages by team name - heavy and not guaranteed.
    return None, None

def edit_submission_with_score(reddit, submission_id, ft_line):
    try:
        submission = reddit.submission(id=submission_id)
        # Prepend FT line to existing content
        original = submission.selftext or ""
        new_body = ft_line + "\n\n" + original
        submission.edit(new_body)
        print(f"Edited submission {submission_id} with: {ft_line}")
        return True
    except Exception as e:
        print(f"Failed to edit submission {submission_id}: {e}")
        return False

def main():
    posted = load_posted()
    if not posted:
        print("No posted entries found.")
        return

    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT")
    )

    updated = False
    for entry in posted:
        # only check matches we posted and haven't posted results for
        if entry.get("result_posted"):
            continue
        submission_id = entry.get("submission_id")
        if not submission_id:
            continue

        status, score_line = fetch_final_score_for_entry(entry)
        if status and score_line:
            ok = edit_submission_with_score(reddit, submission_id, score_line)
            if ok:
                entry["result_posted"] = True
                entry["result_fetched_at"] = datetime.now(ZoneInfo("UTC")).isoformat()
                updated = True

    if updated:
        save_posted(posted)
        print("Updated posted.json with results.")
    else:
        print("No finished matches detected yet.")

if __name__ == "__main__":
    main()
