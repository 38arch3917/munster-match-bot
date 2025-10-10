# munster_bot.py
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

BROADCAST_WHITELIST = ["Premier Sports", "TG4", "RTÉ 2", "Access Munster", "URC.tv"]

IST = pytz.timezone("Europe/Dublin")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# ---------------- HELPERS ----------------
def safe_get(url, timeout=20):
    try:
        r = requests.get(url, timeout=timeout, headers=HEADERS)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"❌ Error fetching URL {url}: {e}")
        return None

def month_name_to_number(name):
    m = {"January":1,"February":2,"March":3,"April":4,"May":5,"June":6,
         "July":7,"August":8,"September":9,"October":10,"November":11,"December":12,
         "Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
    return m.get(name,0)

def parse_datetime_from_line(line):
    clean = re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', line, flags=re.I)
    regex = re.compile(
        r'(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})[,|\s]*'
        r'(?:(?P<hour>\d{1,2}):(?P<minute>\d{2})(?P<ampm>am|pm|AM|PM)?)?'
        r'(?:\s*(?P<tz>[A-Za-z]{2,5}))?', flags=re.I)
    m = regex.search(clean)
    if not m: return None
    day = int(m.group('day'))
    month = month_name_to_number(m.group('month'))
    year = int(m.group('year'))
    hour = int(m.group('hour')) if m.group('hour') else 0
    minute = int(m.group('minute')) if m.group('minute') else 0
    ampm = m.group('ampm')
    tz_abbr = m.group('tz') or ""
    if ampm:
        ampm = ampm.lower()
        if ampm == 'pm' and hour != 12: hour += 12
        if ampm == 'am' and hour == 12: hour = 0
    tz_map = {"BST":"Europe/London","GMT":"Europe/London","WET":"Europe/London",
              "CET":"Europe/Paris","SAST":"Africa/Johannesburg","NZST":"Pacific/Auckland",
              "AEST":"Australia/Sydney","IST":"Europe/Dublin","UTC":"UTC"}
    tz_name = tz_map.get(tz_abbr.upper(),"Europe/Dublin")
    try:
        dt_naive = datetime(year, month, day, hour, minute)
        tz = pytz.timezone(tz_name)
        dt_local = tz.localize(dt_naive)
        return dt_local.astimezone(pytz.utc)
    except Exception as e:
        print(f"❌ Failed to parse datetime from '{line}': {e}")
        return None

def extract_lineup_from_teams_text(text, team_name):
    idx = text.find(team_name)
    if idx == -1: return []
    tail = text[idx:idx+800]
    lines = [l.strip() for l in tail.splitlines() if l.strip()]
    starters = []
    for l in lines:
        if re.match(r'^Substitutes',l,flags=re.I): break
        if len(l.split())>=2 and re.match(r'^[A-Za-z\'\-\.\s]+$',l) and not any(c.isdigit() for c in l):
            starters.append(l)
    if len(starters)<15:
        condensed = re.findall(r'\d+\s+([A-Z][a-zA-Z\'\-\.\s]+?)(?=\s+\d+\s+|$)', tail)
        condensed2 = [c.strip() for c in condensed if len(c.strip().split())>=1]
        if len(condensed2)>=len(starters): starters=condensed2
    return starters[:15]

def already_posted_url(url):
    if not os.path.exists(MATCH_HISTORY_FILE): return False
    try:
        with open(MATCH_HISTORY_FILE) as f:
            data=json.load(f)
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

# ---------------- SCRAPING ----------------
def find_next_munster_match():
    # First try RugbyPass
    r = safe_get(FIXTURES_URL_RP)
    if r:
        soup = BeautifulSoup(r.text,"html.parser")
        anchors = soup.select("a[href*='/live/'], a[href*='/live']")
        seen = set()
        for a in anchors:
            href = a.get("href")
            if not href: continue
            full = href if href.startswith("http") else "https://www.rugbypass.com"+href
            if full in seen or already_posted_url(full): continue
            seen.add(full)
            text = a.get_text(" ",strip=True)
            if TEAM_NAME.lower() in text.lower() or "munster" in full.lower(): return full
    # Backup: UnitedRugby.com
    r2 = safe_get(FIXTURES_URL_URC)
    if r2:
        soup2 = BeautifulSoup(r2.text,"html.parser")
        anchors = soup2.select("a[href*='/fixtures/']")
        for a in anchors:
            href = a.get("href")
            if not href: continue
            full = href if href.startswith("http") else "https://www.unitedrugby.com"+href
            text = a.get_text(" ",strip=True)
            if TEAM_NAME.lower() in text.lower() and not already_posted_url(full):
                return full
    return None

def scrape_match_and_teams(match_url):
    r = safe_get(match_url)
    if not r: return None
    soup = BeautifulSoup(r.text,"html.parser")
    text = soup.get_text("\n",strip=True)

    home,away = None,None
    sel_home = soup.select_one(".fixture__team--home .fixture__team-name")
    sel_away = soup.select_one(".fixture__team--away .fixture__team-name")
    if sel_home and sel_away: home,away = sel_home.get_text(strip=True),sel_away.get_text(strip=True)
    else:
        title = soup.select_one("h1")
        if title and " vs " in title.get_text():
            parts = [p.strip() for p in re.split(r'\s+v(?:s|ersus)\.?\s+|\s+vs\.?\s+',title.get_text(strip=True),flags=re.I)]
            if len(parts)>=2: home,away=parts[0],parts[1]
    home=home or "Munster"; away=away or "Opponent"

    competition,venue,kickoff_dt_utc = None,"TBC",None
    month_regex = re.compile(r'\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b',flags=re.I)
    lines=text.splitlines()
    date_line=None
    for i,line in enumerate(lines[:300]):
        if month_regex.search(line) and re.search(r'\d{4}',line):
            date_line=line.strip()
            for j in range(i,min(i+6,len(lines))):
                ln=lines[j].strip()
                if any(w in ln for w in ('Stadium','Park','Arena','Ground','St.')): venue=ln; break
            for k in range(max(0,i-6),i+1):
                ln2=lines[k].strip()
                if any(x in ln2 for x in ('Championship','Champions','URC','Friendly')): competition=ln2; break
            break
    kickoff_dt_utc = parse_datetime_from_line(date_line) if date_line else None
    is_live = bool(re.search(r'\bLIVE\b',"\n".join(lines[:40]),re.I))

    teams_anchor = soup.find('a', string=re.compile(r'\bTeams\b', re.I))
    teams_url = teams_anchor.get("href") if teams_anchor else match_url.rstrip("/")+"/teams/"
    if teams_url and not teams_url.startswith("http"): teams_url="https://www.rugbypass.com"+teams_url

    lineups={home:[],away:[]}
    teams_page_resp = safe_get(teams_url)
    if teams_page_resp:
        teams_soup = BeautifulSoup(teams_page_resp.text,"html.parser")
        teams_text = teams_soup.get_text("\n",strip=True)
        lineups[home]=extract_lineup_from_teams_text(teams_text,home)
        lineups[away]=extract_lineup_from_teams_text(teams_text,away)
        if (not competition) or competition=="Fixture":
            if 'United Rugby Championship' in teams_text or 'URC' in teams_text: competition='United Rugby Championship'
        if venue=="TBC":
            for ln in teams_text.splitlines():
                if any(w in ln for w in ("Stadium","Park","Arena","Ground","St.")): venue=ln.strip(); break

    competition=competition or "Fixture"
    kickoff_dt_utc = kickoff_dt_utc or (datetime.now(pytz.utc) if is_live else None)
    comp_short = competition
    if 'United Rugby Championship' in competition or 'URC' in competition: comp_short='URC'
    elif 'Champions Cup' in competition or 'Heineken Champions Cup' in competition: comp_short='Champions Cup'

    broadcasters=[]
    b_imgs = soup.select(".fixture__broadcasters img")
    if b_imgs:
        for bi in b_imgs:
            alt = bi.get("alt") or bi.get("title") or ""
            if any(w in alt for w in BROADCAST_WHITELIST): broadcasters.append(alt)

    return {"url":match_url,"teams":f"{home} vs. {away}","home":home,"away":away,
            "competition":comp_short,"venue":venue,"datetime":kickoff_dt_utc,
            "is_live":is_live,"broadcasters":broadcasters,"lineups":lineups}

# ---------------- REDDIT ----------------
def reddit_client():
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("USER_AGENT") or "MunsterKickoffBot/1.0"
    )

def post_match_thread(match):
    reddit = reddit_client()
    subreddit = reddit.subreddit(SUBREDDIT)

    dt_ist = match["datetime"].astimezone(IST)
    title = f"Match Thread: {match['teams']} ({match['competition']}) - {dt_ist.strftime('%A %d %b %Y @ %H:%M')} (IST) - {match['venue']}"

    body_lines=[
        f"🏉 **Kickoff:** {dt_ist.strftime('%A %d %B %Y @ %H:%M (IST)')} - {match['venue']}",
        "",
        f"🏆 **Competition:** {match['competition']}"
    ]
    if match["broadcasters"]: 
        body_lines+=["","📺 **Broadcasters:** "+", ".join(match["broadcasters"])]
    body_lines+=["","🏉 **Starting XV:**","",f"| # | {match['home']} | {match['away']} |","|:--:|:--:|:--:|"]
    for i in range(15):
        h = match["lineups"][match["home"]][i] if i<len(match["lineups"][match["home"]]) else ""
        a = match["lineups"][match["away"]][i] if i<len(match["lineups"][match["away"]]) else ""
        h = h.replace("|","\\|")
        a = a.replace("|","\\|")
        body_lines.append(f"| {i+1} | {h} | {a} |")
    body_lines+=["","**Stand Up And Fight! 💪🔴**","","---","_Automated by /u/MunsterKickoff 🤖_"]
    body="\n".join(body_lines)

    try:
        submission = subreddit.submit(title, selftext=body, flair_id=FLAIR_ID)
        try: submission.mod.distinguish(sticky=True)
        except Exception: pass
        print(f"✅ Posted: {title}")
        save_posted_url(match["url"])
    except Exception as e:
        print("❌ Reddit submission failed:",e)

# ---------------- MAIN ----------------
def main(force_post=False):
    match_link = find_next_munster_match()
    if not match_link: 
        print("No upcoming unposted Munster match found. Exiting.")
        return

    match = scrape_match_and_teams(match_link)
    if not match: 
        print("Failed to scrape match. Exiting.")
        return

    if already_posted_url(match["url"]):
        print("Already posted this match. Exiting.")
        return

    now_utc = datetime.now(pytz.utc)
    post_time = match["datetime"] - timedelta(hours=POST_BEFORE_HOURS) if match["datetime"] else now_utc
    will_post = force_post or match.get("is_live",False) or (match["datetime"] and now_utc>=post_time)
    if not will_post and match["datetime"] and abs((now_utc-match["datetime"]).total_seconds())<7200: 
        will_post=True

    if will_post:
        print("Posting match thread now...")
        post_match_thread(match)
    else:
        print(f"⏳ Not time yet. Kickoff (UTC): {match['datetime']} | Scheduled post time (UTC): {post_time}")

if __name__=="__main__":
    import sys
    force = "--force" in sys.argv or os.getenv("FORCE_POST","0")=="1"
    main(force_post=force)
