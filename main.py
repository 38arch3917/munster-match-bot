import requests
from bs4 import BeautifulSoup
import praw
from datetime import datetime, timedelta
import pytz
from dateutil import parser
from dateutil.relativedelta import relativedelta
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Reddit credentials from environment (GitHub secrets)
reddit = praw.Reddit(
    client_id=os.environ['REDDIT_CLIENT_ID'],
    client_secret=os.environ['REDDIT_CLIENT_SECRET'],
    username=os.environ['REDDIT_USERNAME'],
    password=os.environ['REDDIT_PASSWORD'],
    user_agent='munster_rugby_bot v1.0'
)

SUBREDDIT = 'MunsterRugby'

def normalize(s):
    return s.lower().replace(' v ', ' vs. ').replace('v', 'vs').replace('munster', '').replace(' ', '').strip()

def scrape_kickoff_fixtures():
    url = 'https://www.rugbykickoff.com/Munster/'
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    fixtures = []
    date_headers = soup.find_all('h3')  # Date like "Saturday 18 October"
    for date_h3 in date_headers:
        date_str = date_h3.text.strip()
        time_h4 = date_h3.find_next('h4')
        if not time_h4:
            continue
        time_str = time_h4.text.strip()
        
        opponent_a = time_h4.find_next('a')
        if not opponent_a:
            continue
        opponent = opponent_a.text.strip().replace('v', 'vs.')  # e.g., "Leinster vs. Munster"
        game_href = opponent_a['href']
        game_url = 'https://www.rugbykickoff.com' + game_href
        
        comp_venue_p = opponent_a.find_next('p')
        if not comp_venue_p:
            continue
        comp_venue = comp_venue_p.text.strip().split(' - ')
        competition = comp_venue[0] if len(comp_venue) > 0 else 'Unknown'
        venue = comp_venue[1] if len(comp_venue) > 1 else 'TBA'
        
        # Get detailed broadcasters from game page
        broadcasters = get_broadcasters(game_url)
        
        fixtures.append({
            'date_str': date_str,
            'time_str': time_str,
            'opponent': opponent,
            'competition': competition,
            'venue': venue,
            'game_url': game_url,
            'broadcasters': broadcasters,
            'time_zone': 'US/Eastern'
        })
    return fixtures if fixtures else []

def get_broadcasters(game_url):
    try:
        response = requests.get(game_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        tv_section = soup.find('h3', string=lambda t: 'TV' in t if t else False)  # "Where's the match on TV?"
        if not tv_section:
            return 'TBA'
        
        ireland_h4 = tv_section.find_next('h4', string='Ireland:')
        if not ireland_h4:
            return 'TBA'
        
        broadcasters = []
        a_tags = ireland_h4.find_next_siblings('a', limit=5)  # Up to 5 to avoid extras
        for a in a_tags:
            if a.text.strip():
                broadcasters.append(a.text.strip())
        
        return ' & '.join(broadcasters) if broadcasters else 'TBA'
    except:
        return 'TBA'

def scrape_official_fixtures():
    url = 'https://www.munsterrugby.ie/munster-rugby-fixtures-results/'
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.get(url)
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    driver.quit()
    
    fixtures = []
    now = datetime.now(pytz.timezone('Europe/Dublin'))
    # Assume table structure; adjust selectors if needed (e.g., if div-based, use soup.find_all('div', class_='fixture-row'))
    table = soup.find('table', class_='fixtures-table')  # Add class if present; check page source
    if not table:
        table = soup.find('table')  # Fallback to first table
    if table:
        for row in table.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) < 5:
                continue
            date_str = cols[0].text.strip()
            time_str = cols[1].text.strip()
            opponent = cols[2].text.strip().replace(' v ', ' vs. ')
            venue = cols[3].text.strip()
            competition = cols[4].text.strip()
            broadcasters = cols[5].text.strip() if len(cols) > 5 else 'TBA'
            
            try:
                dt_ist = parse_datetime_general({
                    'date_str': date_str,
                    'time_str': time_str,
                    'time_zone': 'Europe/Dublin'
                })
                if dt_ist > now:
                    fixtures.append({
                        'date_str': date_str,
                        'time_str': time_str,
                        'opponent': opponent,
                        'competition': competition,
                        'venue': venue,
                        'broadcasters': broadcasters,
                        'game_url': None,
                        'time_zone': 'Europe/Dublin'
                    })
            except:
                continue
    return fixtures if fixtures else []

def parse_datetime_general(fixture):
    now = datetime.now(pytz.utc)
    parsed = parser.parse(f'{fixture["date_str"]} {fixture["time_str"]}')
    dt = parsed.replace(year=now.year if parsed.year == 1900 else parsed.year)  # dateutil defaults to 1900 if no year
    if dt < now:
        dt += relativedelta(years=1)
    
    tz = pytz.timezone(fixture['time_zone'])
    dt_local = tz.localize(dt)
    
    dublin = pytz.timezone('Europe/Dublin')
    dt_ist = dt_local.astimezone(dublin)
    return dt_ist

def find_matching_official(kickoff_fixture, official_fixtures):
    k_dt = parse_datetime_general(kickoff_fixture)
    k_norm_opp = normalize(kickoff_fixture['opponent'])
    for off in official_fixtures:
        o_dt = parse_datetime_general(off)
        o_norm_opp = normalize(off['opponent'])
        if abs(k_dt - o_dt) < timedelta(hours=12) and k_norm_opp == o_norm_opp:
            return off
    return None

def comp_short(competition):
    if 'United Rugby Championship' in competition:
        return 'URC'
    elif 'Champions Cup' in competition:
        return 'Champions Cup'
    else:
        return competition  # Full if unknown

def build_title(opponent, dt_ist, comp_short, venue):
    date_fmt = dt_ist.strftime('%a %d %b %Y')
    time_fmt = dt_ist.strftime('%H:%M')
    return f'🏉Match Thread: {opponent} | {date_fmt} | {time_fmt} (IST) | {comp_short} | {venue}'

def build_body(dt_ist, venue, competition, broadcasters):
    date_fmt = dt_ist.strftime('%a %d %b %Y')
    time_fmt = dt_ist.strftime('%H:%M')
    return f"""🏉 **Kickoff:** {date_fmt} @ {time_fmt} (IST)

📍 **Venue:** {venue}

🏆 **Competition:** {competition}

📺 **Broadcasters:** {broadcasters}

It’s all to play for! Drop your thoughts as the match unfolds — COME ON MUNSTER! 🔥🔴🦌

---

**Stand Up and Fight! 💪🔴**

*Automated by /u/MunsterKickoff 🤖*"""

def post_exists(title):
    sub = reddit.subreddit(SUBREDDIT)
    results = sub.search(f'title:"{title}"', sort='new', time_filter='year')
    return any(results)

def main():
    now = datetime.now(pytz.timezone('Europe/Dublin'))
    
    kickoff_fixtures = []
    official_fixtures = []
    
    try:
        kickoff_fixtures = scrape_kickoff_fixtures()
    except Exception as e:
        print(f'Kickoff site error: {e}')
    
    try:
        official_fixtures = scrape_official_fixtures()
    except Exception as e:
        print(f'Official site error: {e}')
    
    if not kickoff_fixtures and not official_fixtures:
        print('No fixtures from either site.')
        return
    
    if not kickoff_fixtures:
        fixtures = official_fixtures
    else:
        fixtures = []
        for k in kickoff_fixtures:
            matching_off = find_matching_official(k, official_fixtures)
            if matching_off:
                # Cross-check and update with official data
                if matching_off['venue'] and (k['venue'] == 'TBA' or k['venue'] != matching_off['venue']):
                    k['venue'] = matching_off['venue']
                if normalize(k['opponent']) != normalize(matching_off['opponent']):
                    k['opponent'] = matching_off['opponent']
                off_dt = parse_datetime_general(matching_off)
                k_dt = parse_datetime_general(k)
                if abs(off_dt - k_dt) >= timedelta(minutes=1):  # Allow minor diffs
                    k['time_str'] = matching_off['time_str']
                    k['date_str'] = matching_off['date_str']
                    k['time_zone'] = matching_off['time_zone']
                    print(f'Time mismatch for {k["opponent"]}, using official.')
                if k['broadcasters'] == 'TBA' and matching_off['broadcasters'] != 'TBA':
                    k['broadcasters'] = matching_off['broadcasters']
            fixtures.append(k)
    
    for fixture in fixtures:
        dt_ist = parse_datetime_general(fixture)
        if dt_ist <= now:
            continue  # Skip past matches
        
        post_time = dt_ist - relativedelta(hours=2)  # Post 2 hour before
        if post_time <= now < dt_ist:
            title = build_title(fixture['opponent'], dt_ist, comp_short(fixture['competition']), fixture['venue'])
            if not post_exists(title):
                body = build_body(dt_ist, fixture['venue'], fixture['competition'], fixture['broadcasters'])
                sub = reddit.subreddit(SUBREDDIT)
                sub.submit(title, selftext=body, send_replies=False)
                print(f'Posted: {title}')  # For logs

if __name__ == '__main__':
    main()
