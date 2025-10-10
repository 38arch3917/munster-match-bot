# munster_bot_final_verified.py
import os
import re
import json
import pytz
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import praw

# ---------------- CONFIG ----------------
TEAM_NAME = "Munster"
SUBREDDIT = "Munsterrugby"
MATCH_HISTORY_FILE = "posted.json"
FLAIR_ID = "44ddc6a8-a2a2-11f0-ab19-0257fc8eb3f2"
POST_BEFORE_HOURS = 4

FIXTURES_URL_RP = "https://www.rugbypass.com/teams/munster/fixtures-results/"
FIXTURES_URL_URC = "https://www.unitedrugby.com/clubs/munster/fixtures"
FIXTURES_URL_OFFICIAL = "https://www.munsterrugby.ie/fixtures-results/"

BROADCAST_WHITELIST = ["Premier Sports", "TG4", "RTÉ 2", "Access Munster", "URC.tv"]

IST = pytz.timezone("Europe/Dublin")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# ---------------- HELPERS ----------------
def safe_get(url, timeout=20):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"❌ Error fetching {url}: {e}")
        return None

def already_posted_url(url):
    if not os.path.exists(MATCH_HISTORY_FILE): return False
    try:
        with open(MATCH_HISTORY_FILE) as f:
            data = json.load(f)
        return url in data
    except Exception:
        return False

def save_posted_url(url):
    data=[]
    if os.path.exists(MATCH_HISTORY_FILE):
        try:
            with open(MATCH_HISTORY_FILE) as f:
                data=json.load(f)
        except Exception:
            data=[]
    data.append(url)
    with open(MATCH_HISTORY_FILE,"w") as f:
        json.dump(data,f)

def parse_datetime(text):
    """Parse date/time string into UTC datetime."""
    text = re.sub(r'(\d)(st|nd|rd|th)', r'\1', text, flags=re.I)
    regex = re.compile(
        r'(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})[,|\s]*'
        r'(?:(?P<hour>\d{1,2}):(?P<minute>\d{2})(?P<ampm>am|pm)?)?'
        r'(?:\s*(?P<tz>[A-Za-z]{2,5}))?', flags=re.I)
    m = regex.search(text)
    if not m: return None
    day = int(m.group('day'))
    month = datetime.strptime(m.group('month')[:3], "%b").month
    year = int(m.group('year'))
    hour = int(m.group('hour')) if m.group('hour') else 0
    minute = int(m.group('minute')) if m.group('minute') else 0
    ampm = m.group('ampm')
    tz_abbr = m.group('tz') or ""
    if ampm:
        ampm = ampm.lower()
        if ampm=="pm" and hour!=12: hour+=12
        if ampm=="am" and hour==12: hour=0
    tz_map = {"BST":"Europe/London","GMT":"Europe/London","IST":"Europe/Dublin","UTC":"UTC"}
    tz_name = tz_map.get(tz_abbr.upper(),"Europe/Dublin")
    try:
        dt_naive = datetime(year, month, day, hour, minute)
        tz = pytz.timezone(tz_name)
        dt_local = tz.localize(dt_naive)
        return dt_local.astimezone(pytz.utc)
    except Exception:
        return None

def extract_lineup(text, team_name):
    """Extract 15-man Starting XV from team section."""
    idx = text.find(team_name)
    if idx==-1: return []
    snippet = text[idx:idx+1000]
    lines = [l.strip() for l in snippet.splitlines() if l.strip()]
    starters=[]
    for l in lines:
        if re.match(r'^Substitutes',l,flags=re.I): break
        if len(l.split())>=2 and re.match(r'^[A-Za-z\'\-\.\s]+$',l) and not any(c.isdigit() for c in l):
            starters.append(l)
    if len(starters)<15:
        # fallback to regex pattern
        condensed = re.findall(r'\d+\s+([A-Z][a-zA-Z\'\-\.\s]+?)(?=\s+\d+\s+|$)', snippet)
        starters = [c.strip() for c in condensed if len(c.strip().split())>=1]
    return starters[:15]

# ---------------- SCRAPING ----------------
def fetch_next_match_rp():
    r = safe_get(FIXTURES_URL_RP)
    if not r: return None
    soup = BeautifulSoup(r.text,"html.parser")
    anchors = soup.select("a[href*='/live/'], a[href*='/live']")
    for a in anchors:
        href = a.get("href")
        full = href if href.startswith("http") else "https://www.rugbypass.com"+href
        if TEAM_NAME.lower() in a.get_text(" ",strip=True).lower() and not already_posted_url(full):
            return full
    return None

def fetch_next_match_urc():
    r = safe_get(FIXTURES_URL_URC)
    if not r: return None
    soup = BeautifulSoup(r.text,"html.parser")
    anchors = soup.select("a[href*='/fixtures/']")
    for a in anchors:
        full = a.get("href")
        full = full if full.startswith("http") else "https://www.unitedrugby.com"+full
        if TEAM_NAME.lower() in a.get_text(" ",strip=True).lower() and not already_posted_url(full):
            return full
    return None

def fetch_next_match_official():
    r = safe_get(FIXTURES_URL_OFFICIAL)
    if not r: return None
    soup = BeautifulSoup(r.text,"html.parser")
    anchors = soup.select("a[href*='/fixtures/'],a[href*='/match/']")
    for a in anchors:
        full = a.get("href")
        full = full if full.startswith("http") else "https://www.munsterrugby.ie"+full
        if not already_posted_url(full):
            return full
    return None

def find_next_munster_match():
    # Try RP -> URC -> Official Munster
    for fn in [fetch_next_match_rp, fetch_next_match_urc, fetch_next_match_official]:
        url = fn()
        if url: return url
    return None

def scrape_match(match_url):
    r = safe_get(match_url)
    if not r: return None
    soup = BeautifulSoup(r.text,"html.parser")
    text = soup.get_text("\n",strip=True)

    # Teams
    home,away=None,None
    sel_home = soup.select_one(".fixture__team--home .fixture__team-name")
    sel_away = soup.select_one(".fixture__team--away .fixture__team-name")
    if sel_home and sel_away:
        home,away = sel_home.get_text(strip=True),sel_away.get_text(strip=True)
    else:
        h1 = soup.select_one("h1")
        if h1 and " vs " in h1.get_text():
            parts = [p.strip() for p in re.split(r'\s+v(?:s|ersus)?\.?\s+',h1.get_text(strip=True),flags=re.I)]
            if len(parts)>=2: home,away=parts[0],parts[1]
    home = home or "Munster"; away = away or "Opponent"

    # Date/Competition/Venue
    competition = venue = None
    kickoff_dt = None
    month_regex = re.compile(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\b',flags=re.I)
    for line in text.splitlines()[:300]:
        if month_regex.search(line) and re.search(r'\d{4}',line): kickoff_dt=parse_datetime(line)
        if any(x in line for x in ['Championship','URC','Champions Cup','Friendly']): competition=line
        if any(x in line for x in ['Stadium','Park','Arena','Ground','St.']): venue=line
    competition = competition or "Fixture"
    kickoff_dt = kickoff_dt or datetime.now(pytz.utc)
    if 'United Rugby Championship' in competition or 'URC' in competition: competition='URC'
    elif 'Champions Cup' in competition: competition='Champions Cup'

    # Lineups
    teams_anchor = soup.find('a', string=re.compile(r'\bTeams\b', re.I))
    teams_url = teams_anchor.get("href") if teams_anchor else match_url.rstrip("/")+"/teams/"
    if teams_url and not teams_url.startswith("http"): teams_url="https://www.rugbypass.com"+teams_url
    lineups={home:[],away:[]}
    teams_page = safe_get(teams_url)
    if teams_page:
        teams_text = BeautifulSoup(teams_page.text,"html.parser").get_text("\n",strip=True)
        lineups[home] = extract_lineup(teams_text,home)
        lineups[away] = extract_lineup(teams_text,away)

    # Broadcasters
    broadcasters=[]
    b_imgs = soup.select(".fixture__broadcasters img")
    for bi in b_imgs:
        alt = bi.get("alt") or bi.get("title") or ""
        if any(b in alt for b in BROADCAST_WHITELIST): broadcasters.append(alt)

    return {"url":match_url,"teams":f"{home} vs. {away}","home":home,"away":away,
            "competition":competition,"venue":venue,"datetime":kickoff_dt,
            "lineups":lineups,"broadcasters":broadcasters}

# ---------------- REDDIT ----------------
def reddit_client():
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT") or "MunsterKickoffBot/1.0"
    )

def post_match(match):
    reddit = reddit_client()
    subreddit = reddit.subreddit(SUBREDDIT)
    dt_ist = match["datetime"].astimezone(IST)
    title = f"Match Thread: {match['teams']} ({match['competition']}) - {dt_ist.strftime('%A %d %b %Y @ %H:%M')} (IST) - {match['venue']}"
    body=[
        f"🏉 **Kickoff:** {dt_ist.strftime('%A %d %B %Y @ %H:%M (IST)')} - {match['venue']}",
        "",
        f"🏆 **Competition:** {match['competition']}"
    ]
    if match["broadcasters"]:
        body+=["","📺 **Broadcasters:** "+", ".join(match["broadcasters"])]
    body+=["","🏉 **Starting XV:**","",f"| # | {match['home']} | {match['away']} |","|:--:|:--:|:--:|"]
    for i in range(15):
        h = match["lineups"][match["home"]][i] if i<len(match["lineups"][match["home"]]) else ""
        a = match["lineups"][match["away"]][i] if i<len(match["lineups"][match["away"]]) else ""
        h = h.replace("|","\\|"); a = a.replace("|","\\|")
        body.append(f"| {i+1} | {h} | {a} |")
    body+=["","**Stand Up And Fight! 💪🔴**","","---","_Automated by /u/MunsterKickoff 🤖_"]
    try:
        submission = subreddit.submit(title,selftext="\n".join(body),flair_id=FLAIR_ID)
        try: submission.mod.distinguish(sticky=True)
        except: pass
        print(f"✅ Posted: {title}")
        save_posted_url(match["url"])
    except Exception as e:
        print("❌ Reddit submission failed:",e)

# ---------------- MAIN ----------------
def main(force_post=False):
    match_link = find_next_munster_match()
    if not match_link:
        print("No upcoming unposted Munster match found.")
        return
    match = scrape_match(match_link)
    if not match:
        print("Failed to scrape match data.")
        return
    if already_posted_url(match["url"]):
        print("Match already posted.")
        return
    now = datetime.now(pytz.utc)
    post_time = match["datetime"] - timedelta(hours=POST_BEFORE_HOURS)
    if force_post or now>=post_time:
        post_match(match)
    else:
        print(f"⏳ Not posting yet. Kickoff UTC: {match['datetime']} | Post UTC: {post_time}")

if __name__=="__main__":
    import sys
    force = "--force" in sys.argv or os.getenv("FORCE_POST","0")=="1"
    main(force_post=force)
