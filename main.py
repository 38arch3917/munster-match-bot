import requests
from bs4 import BeautifulSoup
import praw
from datetime import datetime, timedelta
import pytz
from dateutil import parser
from dateutil.relativedelta import relativedelta
import os
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

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

def normalize(s):
    return s.lower().replace(' v ', ' vs. ').replace('v', 'vs').replace('munster', '').replace(' ', '').strip()

def scrape_kickoff_fixtures():
    url = 'https://www.rugbykickoff.com/Munster/'
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        logging.info(f"Kickoff soup title: {soup.title.string if soup.title else 'No title'}")
        
        fixtures = []
        date_headers = soup.find_all('h2')  # Date headers
        logging.info(f"Found {len(date_headers)} date headers (h2)")
        for date_h2 in date_headers:
            date_str = date_h2.text.strip()
            current = date_h2.next_sibling
            while current:
                if current.name == 'h3':
                    time_str = current.text.strip()
                elif current.name == 'a':
                    opponent = current.text.strip().replace('v', 'vs.')
                    game_href = current['href']
                    game_url = 'https://www.rugbykickoff.com' + game_href if game_href.startswith('/') else game_href
                elif current.name == 'p':
                    if ' - ' in current.text:
                        comp_venue = current.text.strip().split(' - ')
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
                            'time_zone': 'US/Eastern'
                        })
                        logging.debug(f"Scraped: {opponent} on {date_str} at {time_str}, venue: {venue}")
                current = current.next_sibling
                if current and current.name == 'h2':  # Stop at next date
                    break
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
        
        tv_section = soup.find('h3', string=lambda t: t and 'TV' in t)
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
    except Exception as e:
        logging.warning(f'Broadcasters fetch error for {game_url}: {e}')
        return 'TBA'

def scrape_official_fixtures():
    url = 'https://www.munsterrugby.ie/munster-rugby-fixtures-results/'
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(15)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        logging.info(f"Official soup title: {soup.title.string if soup.title else 'No title'}")
        
        fixtures = []
        now = datetime.now(pytz.timezone('Europe/Dublin'))
        
        # Try table
        table = soup.find('table')
        if table:
            logging.info("Found table structure")
            for row in table.find_all('tr')[1:]:
                cols = row.find_all('td')
                if len(cols) < 4:
                    continue
                date_str = cols[0].text.strip()
                time_str = cols[1].text.strip()
                opponent = cols[2].text.strip().replace(' v ', ' vs. ')
                venue = cols[3].text.strip()
                competition = cols[4].text.strip() if len(cols) > 4 else 'Unknown'
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
                except Exception as parse_e:
                    logging.warning(f"Parse error for row {date_str}: {parse_e}")
                    continue
        else:
            # Div fallback with broader search
            logging.info("No table, trying fixture divs")
            fixture_divs = soup.find_all('div', class_=lambda x: x and any(term in x.lower() for term in ['fixture', 'match', 'event', 'result', 'game', 'card']))
            logging.info(f"Found {len(fixture_divs)} targeted fixture divs")
            for div in fixture_divs:
                text = div.text.strip()
                if '2025' in text or '2026' in text:  # Filter for future
                    logging.info(f"Sample fixture div text: {text[:500]}...")
                    # Split text (e.g., "Sat 25 Oct 19:45 Connacht Thomond Park URC")
                    parts = text.split()
                    if len(parts) < 5:
                        continue
                    date_str = ' '.join(parts[:3])  # e.g., Sat 25 Oct
                    time_str = parts[3]
                    opponent = ' '.join(parts[4:6]).replace('v', 'vs.')  # e.g., vs. Connacht
                    venue = ' '.join(parts[6:8])  # e.g., Thomond Park
                    competition = ' '.join(parts[8:])  # e.g., URC
                    broadcasters = 'TBA'
                    
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
                    except Exception as parse_e:
                        logging.warning(f"Div parse error for {date_str}: {parse_e}")
                        continue
        
        logging.info(f"✓ Scraped {len(fixtures)} official fixtures")
        return fixtures
    except TimeoutException:
        logging.error("Selenium timeout—JS load failed")
    except Exception as e:
        logging.error(f'Official site error: {e}')
    finally:
        driver.quit()
    return []

def parse_datetime_general(fixture):
    now = datetime.now(pytz.utc)
    parsed = parser.parse(f'{fixture["date_str"]} {fixture["time_str"]}')
    dt = parsed.replace(year=now.year if parsed.year == 1900 else parsed.year)
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
        return competition

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
    try:
        sub = reddit.subreddit(SUBREDDIT)
        results = sub.search(f'title:"{title}"', sort='new', time_filter='year')
        return any(results)
    except Exception as e:
        logging.error(f'Reddit search error: {e}')
        return False

def main():
    now = datetime.now(pytz.timezone('Europe/Dublin'))
    logging.info(f"Bot run at {now}")
    
    kickoff_fixtures = scrape_kickoff_fixtures()
    official_fixtures = scrape_official_fixtures()
    
    if not official_fixtures and kickoff_fixtures:
        logging.info("Official failed—using kickoff data only")
    
    if not kickoff_fixtures and not official_fixtures:
        logging.error('No fixtures from either site.')
        return
    
    if not kickoff_fixtures:
        fixtures = official_fixtures
    else:
        fixtures = []
        for k in kickoff_fixtures:
            matching_off = find_matching_official(k, official_fixtures)
            if matching_off:
                if matching_off['venue'] and (k['venue'] == 'TBA' or k['venue'] != matching_off['venue']):
                    k['venue'] = matching_off['venue']
                    logging.info(f"Updated venue for {k['opponent']}: {k['venue']}")
                if normalize(k['opponent']) != normalize(matching_off['opponent']):
                    k['opponent'] = matching_off['opponent']
                off_dt = parse_datetime_general(matching_off)
                k_dt = parse_datetime_general(k)
                if abs(off_dt - k_dt) >= timedelta(minutes=1):
                    k['time_str'] = matching_off['time_str']
import requests
from bs4 import BeautifulSoup
import praw
from datetime import datetime, timedelta
import pytz
from dateutil import parser
from dateutil.relativedelta import relativedelta
import os
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

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

def normalize(s):
    return s.lower().replace(' v ', ' vs. ').replace('v', 'vs').replace('munster', '').replace(' ', '').strip()

def scrape_kickoff_fixtures():
    url = 'https://www.rugbykickoff.com/Munster/'
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        logging.info(f"Kickoff soup title: {soup.title.string if soup.title else 'No title'}")
        
        fixtures = []
        date_headers = soup.find_all('h2')  # Date headers
        logging.info(f"Found {len(date_headers)} date headers (h2)")
        for date_h2 in date_headers:
            date_str = date_h2.text.strip()
            current = date_h2.next_sibling
            while current:
                if current.name == 'h3':
                    time_str = current.text.strip()
                elif current.name == 'a':
                    opponent = current.text.strip().replace('v', 'vs.')
                    game_href = current['href']
                    game_url = 'https://www.rugbykickoff.com' + game_href if game_href.startswith('/') else game_href
                elif current.name == 'p':
                    if ' - ' in current.text:
                        comp_venue = current.text.strip().split(' - ')
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
                            'time_zone': 'US/Eastern'
                        })
                        logging.debug(f"Scraped: {opponent} on {date_str} at {time_str}, venue: {venue}")
                current = current.next_sibling
                if current and current.name == 'h2':  # Stop at next date
                    break
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
        
        tv_section = soup.find('h3', string=lambda t: t and 'TV' in t)
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
    except Exception as e:
        logging.warning(f'Broadcasters fetch error for {game_url}: {e}')
        return 'TBA'

def scrape_official_fixtures():
    url = 'https://www.munsterrugby.ie/munster-rugby-fixtures-results/'
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(15)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        logging.info(f"Official soup title: {soup.title.string if soup.title else 'No title'}")
        
        fixtures = []
        now = datetime.now(pytz.timezone('Europe/Dublin'))
        
        # Try table
        table = soup.find('table')
        if table:
            logging.info("Found table structure")
            for row in table.find_all('tr')[1:]:
                cols = row.find_all('td')
                if len(cols) < 4:
                    continue
                date_str = cols[0].text.strip()
                time_str = cols[1].text.strip()
                opponent = cols[2].text.strip().replace(' v ', ' vs. ')
                venue = cols[3].text.strip()
                competition = cols[4].text.strip() if len(cols) > 4 else 'Unknown'
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
                except Exception as parse_e:
                    logging.warning(f"Parse error for row {date_str}: {parse_e}")
                    continue
        else:
            # Div fallback with broader search
            logging.info("No table, trying fixture divs")
            fixture_divs = soup.find_all('div', class_=lambda x: x and any(term in x.lower() for term in ['fixture', 'match', 'event', 'result', 'game', 'card']))
            logging.info(f"Found {len(fixture_divs)} targeted fixture divs")
            for div in fixture_divs:
                text = div.text.strip()
                if '2025' in text or '2026' in text:  # Filter for future
                    logging.info(f"Sample fixture div text: {text[:500]}...")
                    # Split text (e.g., "Sat 25 Oct 19:45 Connacht Thomond Park URC")
                    parts = text.split()
                    if len(parts) < 5:
                        continue
                    date_str = ' '.join(parts[:3])  # e.g., Sat 25 Oct
                    time_str = parts[3]
                    opponent = ' '.join(parts[4:6]).replace('v', 'vs.')  # e.g., vs. Connacht
                    venue = ' '.join(parts[6:8])  # e.g., Thomond Park
                    competition = ' '.join(parts[8:])  # e.g., URC
                    broadcasters = 'TBA'
                    
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
                    except Exception as parse_e:
                        logging.warning(f"Div parse error for {date_str}: {parse_e}")
                        continue
        
        logging.info(f"✓ Scraped {len(fixtures)} official fixtures")
        return fixtures
    except TimeoutException:
        logging.error("Selenium timeout—JS load failed")
    except Exception as e:
        logging.error(f'Official site error: {e}')
    finally:
        driver.quit()
    return []

def parse_datetime_general(fixture):
    now = datetime.now(pytz.utc)
    parsed = parser.parse(f'{fixture["date_str"]} {fixture["time_str"]}')
    dt = parsed.replace(year=now.year if parsed.year == 1900 else parsed.year)
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
        return competition

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
    try:
        sub = reddit.subreddit(SUBREDDIT)
        results = sub.search(f'title:"{title}"', sort='new', time_filter='year')
        return any(results)
    except Exception as e:
        logging.error(f'Reddit search error: {e}')
        return False

def main():
    now = datetime.now(pytz.timezone('Europe/Dublin'))
    logging.info(f"Bot run at {now}")
    
    kickoff_fixtures = scrape_kickoff_fixtures()
    official_fixtures = scrape_official_fixtures()
    
    if not official_fixtures and kickoff_fixtures:
        logging.info("Official failed—using kickoff data only")
    
    if not kickoff_fixtures and not official_fixtures:
        logging.error('No fixtures from either site.')
        return
    
    if not kickoff_fixtures:
        fixtures = official_fixtures
    else:
        fixtures = []
        for k in kickoff_fixtures:
            matching_off = find_matching_official(k, official_fixtures)
            if matching_off:
                if matching_off['venue'] and (k['venue'] == 'TBA' or k['venue'] != matching_off['venue']):
                    k['venue'] = matching_off['venue']
                    logging.info(f"Updated venue for {k['opponent']}: {k['venue']}")
                if normalize(k['opponent']) != normalize(matching_off['opponent']):
                    k['opponent'] = matching_off['opponent']
                off_dt = parse_datetime_general(matching_off)
                k_dt = parse_datetime_general(k)
                if abs(off_dt - k_dt) >= timedelta(minutes=1):
                    k['time_str'] = matching_off['time_str']
                    k['date_str'] = matching_off['date_str']
                    k['time_zone'] = matching_off['time_zone']
                    logging.info(f'Time mismatch for {k["opponent"]}, using official.')
import requests
from bs4 import BeautifulSoup
import praw
from datetime import datetime, timedelta
import pytz
from dateutil import parser
from dateutil.relativedelta import relativedelta
import os
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

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

def normalize(s):
    return s.lower().replace(' v ', ' vs. ').replace('v', 'vs').replace('munster', '').replace(' ', '').strip()

def scrape_kickoff_fixtures():
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
            current = date_h2.next_sibling
            time_str = ''
            opponent = ''
            game_url = ''
            competition = ''
            venue = 'TBA'
            while current:
                if hasattr(current, 'name'):
                    if current.name == 'h3':
                        time_str = current.text.strip()
                    elif current.name == 'a':
                        opponent = current.text.strip().replace('v', 'vs.')
                        game_href = current['href']
                        game_url = 'https://www.rugbykickoff.com' + game_href if game_href.startswith('/') else game_href
                    elif current.name == 'p':
                        if ' - ' in current.text:
                            comp_venue = current.text.strip().split(' - ')
                            competition = comp_venue[0] if len(comp_venue) > 0 else 'Unknown'
                            venue = comp_venue[1] if len(comp_venue) > 1 else 'TBA'
                            broadcasters = get_broadcasters(game_url)
                            if opponent and time_str and competition:
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
                                logging.debug(f"Scraped: {opponent} on {date_str} at {time_str}, venue: {venue}")
                current = current.next_sibling if current else None
                if current and hasattr(current, 'name') and current.name == 'h2':
                    break
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
        
        tv_section = soup.find('h3', string=lambda t: t and 'TV' in t)
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
    except Exception as e:
        logging.warning(f'Broadcasters fetch error for {game_url}: {e}')
        return 'TBA'

def scrape_official_fixtures():
    url = 'https://www.munsterrugby.ie/munster-rugby-fixtures-results/'
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(15)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        logging.info(f"Official soup title: {soup.title.string if soup.title else 'No title'}")
        
        fixtures = []
        now = datetime.now(pytz.timezone('Europe/Dublin'))
        
        table = soup.find('table', class_='table table-striped table-responsive')
        if table:
            logging.info("Found table structure with class 'table table-striped table-responsive'")
            for row in table.find_all('tr')[1:]:
                cols = row.find_all('td')
                if len(cols) < 5:
                    continue
                date_str = cols[0].text.strip()
                time_str = cols[1].text.strip()
                opponent = cols[2].text.strip().replace(' v ', ' vs. ')
                venue = cols[3].text.strip()
                competition = cols[4].text.strip()
                broadcasters = 'TBA'  # Assume no column; pull if exists
                
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
                except Exception as parse_e:
                    logging.warning(f"Parse error for row {date_str}: {parse_e}")
                    continue
        else:
            logging.info("No table found, trying alternative structures")
            # ... (keep previous div fallback if needed)
        
        logging.info(f"✓ Scraped {len(fixtures)} official fixtures")
        return fixtures
    except TimeoutException:
        logging.error("Selenium timeout—JS load failed")
    except Exception as e:
        logging.error(f'Official site error: {e}')
    finally:
        driver.quit()
    return []

def parse_datetime_general(fixture):
    now = datetime.now(pytz.utc)
    parsed = parser.parse(f'{fixture["date_str"]} {fixture["time_str"]}')
    dt = parsed.replace(year=now.year if parsed.year == 1900 else parsed.year)
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
        return competition

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
    try:
        sub = reddit.subreddit(SUBREDDIT)
        results = sub.search(f'title:"{title}"', sort='new', time_filter='year')
        return any(results)
    except Exception as e:
        logging.error(f'Reddit search error: {e}')
        return False

def main():
    now = datetime.now(pytz.timezone('Europe/Dublin'))
    logging.info(f"Bot run at {now}")
    
    kickoff_fixtures = scrape_kickoff_fixtures()
    official_fixtures = scrape_official_fixtures()
    
    if not official_fixtures and kickoff_fixtures:
        logging.info("Official failed—using kickoff data only")
    
    if not kickoff_fixtures and not official_fixtures:
        logging.error('No fixtures from either site.')
        return
    
    if not kickoff_fixtures:
        fixtures = official_fixtures
    else:
        fixtures = []
        for k in kickoff_fixtures:
            matching_off = find_matching_official(k, official_fixtures)
            if matching_off:
                if matching_off['venue'] and (k['venue'] == 'TBA' or k['venue'] != matching_off['venue']):
                    k['venue'] = matching_off['venue']
                    logging.info(f"Updated venue for {k['opponent']}: {k['venue']}")
                if normalize(k['opponent']) != normalize(matching_off['opponent']):
                    k['opponent'] = matching_off['opponent']
                off_dt = parse_datetime_general(matching_off)
                k_dt = parse_datetime_general(k)
                if abs(off_dt - k_dt) >= timedelta(minutes=1):
                    k['time_str'] = matching_off['time_str']
                    k['date_str'] = matching_off['date_str']
                    k['time_zone'] = matching_off['time_zone']
                    logging.info(f'Time mismatch for {k["opponent"]}, using official.')
                if k['broadcasters'] == 'TBA' and matching_off['broadcasters'] != 'TBA':
                    k['broadcasters'] = matching_off['broadcasters']
            fixtures.append(k)
    
    logging.info(f"Processing {len(fixtures)} total fixtures")
    for fixture in fixtures:
        dt_ist = parse_datetime_general(fixture)
        if dt_ist <= now:
            continue
        
        post_time = dt_ist - relativedelta(hours=2)  # Post 2 hours before
        if post_time <= now < dt_ist:
            title = build_title(fixture['opponent'], dt_ist, comp_short(fixture['competition']), fixture['venue'])
            if not post_exists(title):
                body = build_body(dt_ist, fixture['venue'], fixture['competition'], fixture['broadcasters'])
                sub = reddit.subreddit(SUBREDDIT)
                submission = sub.submit(title, selftext=body, send_replies=False)
                logging.info(f'Posted: {title} (ID: {submission.id})')
            else:
                logging.info(f'Skipped duplicate: {title}')

if __name__ == '__main__':
    main()
