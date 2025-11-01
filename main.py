import requests
from bs4 import BeautifulSoup
import praw
from datetime import datetime, timedelta
import pytz
from dateutil import parser
from dateutil.relativedelta import relativedelta
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Reddit credentials from environment (GitHub secrets)
reddit = praw.Reddit(
 client_id=os.environ['REDDIT_CLIENT_ID'],
 client_secret=os.environ['REDDIT_CLIENT_SECRET'],
 username=os.environ['REDDIT_USERNAME'],
 password=os.environ['REDDIT_PASSWORD'],
 user_agent='munster_rugby_bot v1.0'
)

SUBREDDIT = 'MunsterRugby'

HEADERS = {
 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def get_current_timezone():
 try:
 response = requests.get('https://ipapi.co/timezone', timeout=5)
 response.raise_for_status()
 tz_str = response.text.strip()
 pytz.timezone(tz_str) # Validate it's a valid tz
 return tz_str
 except Exception as e:
 logging.error(f'Failed to get timezone: {e}. Defaulting to UTC.')
 return 'UTC'

def normalize(s):
 return s.lower().replace(' v ', ' vs. ').replace('v', 'vs').replace('munster', '').replace(' ', '').strip()

def scrape_kickoff_fixtures(time_zone):
 url = 'https://www.rugbykickoff.com/Munster/'
 try:
 response = requests.get(url, headers=HEADERS, timeout=10)
 response.raise_for_status()
 soup = BeautifulSoup(response.text, 'html.parser')
 logging.info(f"Kickoff soup title: {soup.title.string if soup.title else 'No title'}")
 
 fixtures = []
 date_headers = soup.find_all('h2')
 logging.info(f"Found {len(date_headers)} date headers (h2)")
 for date_h2 in date_headers:
 date_str = date_h2.text.strip()
 time_h3 = date_h2.find_next('h3')
 if not time_h3:
 continue
 time_str = time_h3.text.strip()
 
 opponent_a = time_h3.find_next('a')
 if not opponent_a:
 continue
 opponent = opponent_a.text.strip().replace('v', 'vs.')
 game_href = opponent_a['href']
 game_url = 'https://www.rugbykickoff.com' + game_href
 
 comp_venue_p = opponent_a.find_next('p')
 if not comp_venue_p:
 continue
 comp_venue = comp_venue_p.text.strip().split(' - ')
 competition = comp_venue[0] if len(comp_venue) > 0 else 'Unknown'
 venue = comp_venue[1] if len(comp_venue) > 1 else 'TBA'
 
 broadcasters = get_broadcasters(game_url)
 
 fixtures.append({
 'date_str': date_str,
 'time_str': time_str,
 'opponent': opponent,
 'competition': competition,
 'venue': venue,
 'game_url': game_url,
 'broadcasters': broadcasters,
 'time_zone': time_zone
 })
 logging.info(f"✓ Scraped {len(fixtures)} kickoff fixtures")
 return fixtures
 except Exception as e:
 logging.error(f'Kickoff site error: {e}')
 return []

def get_broadcasters(game_url):
 try:
 response = requests.get(game_url, headers=HEADERS, timeout=10)
 response.raise_for_status()
 soup = BeautifulSoup(response.text, 'html.parser')
 
 tv_section = soup.find('h3', string=lambda t: 'TV' in t if t else False)
 if not tv_section:
 return 'TBA'
 
 ireland_h4 = tv_section.find_next('h4', string='Ireland:')
 if not ireland_h4:
 return 'TBA'
 
 broadcasters = []
 a_tags = ireland_h4.find_next_siblings('a', limit=5)
 for a in a_tags:
 if a.text.strip():
 broadcasters.append(a.text.strip())
 
 return ' & '.join(broadcasters) if broadcasters else 'TBA'
 except:
 return 'TBA'

def parse_datetime_general(fixture):
 now = datetime.now(pytz.utc)
 parsed = parser.parse(f'{fixture["date_str"]} {fixture["time_str"]}')
 dt = parsed.replace(year=now.year if parsed.year == 1900 else parsed.year)
 
 tz = pytz.timezone(fixture['time_zone'])
 dt = tz.localize(dt, is_dst=False) # Handle potential DST ambiguity by assuming standard time
 
 if dt < now:
 dt += relativedelta(years=1)
 
 dublin = pytz.timezone('Europe/Dublin')
 dt_ist = dt.astimezone(dublin)
 return dt_ist

def comp_short(competition):
 if 'United Rugby Championship' in competition:
 return 'URC'
 elif 'Champions Cup' in competition:
 return 'Champions Cup'
 else:
 return competition

def build_title(opponent, dt_ist, comp_short, venue):
 date_fmt = dt_ist.strftime('%a %d %b %Y')
 time_fmt = dt_ist.strftime('%H:%M')
 venue_part = f' | {venue}' if venue != 'TBA' else ''
 return f'🏉 Match Thread: {opponent} | {date_fmt} | {time_fmt} (IST) | {comp_short}{venue_part}'

def build_body(dt_ist, venue, competition, broadcasters):
 date_fmt = dt_ist.strftime('%a %d %b %Y')
 time_fmt = dt_ist.strftime('%H:%M')
 venue_line = f'📍 **Venue:** {venue}\n\n' if venue != 'TBA' else ''
 return f"""🏉 **Kickoff:** {date_fmt} @ {time_fmt} (IST)

{venue_line}🏆 **Competition:** {competition}

📺 **Broadcasters:** {broadcasters}

It’s all to play for! Drop your thoughts as the match unfolds — COME ON MUNSTER, SUAF! 🔥💪🔴🦌

---

*Automated by Munster Kickoff Bot*"""

def post_exists(opponent, date_fmt):
 sub = reddit.subreddit(SUBREDDIT)
 query = f'title:"Match Thread: {opponent}" title:"{date_fmt}"'
 results = sub.search(query, sort='new', time_filter='year')
 return any(results)

def main():
 now = datetime.now(pytz.timezone('Europe/Dublin'))
 
 time_zone = get_current_timezone()
 logging.info(f"Detected timezone: {time_zone}")
 
 fixtures = scrape_kickoff_fixtures(time_zone)
 
 if not fixtures:
 print('No fixtures scraped.')
 return
 
 for fixture in fixtures:
 dt_ist = parse_datetime_general(fixture)
 if dt_ist <= now:
 continue
 
 post_time = dt_ist - relativedelta(hours=2) # Post 2 hours before
 if post_time <= now < dt_ist:
 date_fmt = dt_ist.strftime('%a %d %b %Y')
 if not post_exists(fixture['opponent'], date_fmt):
 title = build_title(fixture['opponent'], dt_ist, comp_short(fixture['competition']), fixture['venue'])
 body = build_body(dt_ist, fixture['venue'], fixture['competition'], fixture['broadcasters'])
 sub = reddit.subreddit(SUBREDDIT)
 sub.submit(title, selftext=body, send_replies=False)
 print(f'Posted: {title}')

if __name__ == '__main__':
 main()
