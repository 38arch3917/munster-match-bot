import requests
from bs4 import BeautifulSoup
import praw
from datetime import datetime
import pytz
from dateutil import parser
from dateutil.relativedelta import relativedelta
import os

# Reddit credentials from environment (GitHub secrets)
reddit = praw.Reddit(
    client_id=os.environ['REDDIT_CLIENT_ID'],
    client_secret=os.environ['REDDIT_CLIENT_SECRET'],
    username=os.environ['REDDIT_USERNAME'],
    password=os.environ['REDDIT_PASSWORD'],
    user_agent='munster_rugby_bot v1.0'
)

SUBREDDIT = 'MunsterRugby'

def scrape_fixtures():
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
        opponent = opponent_a.text.strip().replace('v', 'Vs.')  # e.g., "Leinster Vs. Munster"
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
            'broadcasters': broadcasters
        })
    return fixtures

def get_broadcasters(game_url):
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

def parse_datetime(date_str, time_str):
    now = datetime.now(pytz.utc)
    parsed = parser.parse(f'{date_str} {time_str}')
    dt = parsed.replace(year=now.year)
    if dt < now:
        dt += relativedelta(years=1)
    
    # Assume site time is US/Eastern
    eastern = pytz.timezone('US/Eastern')
    dt = eastern.localize(dt)
    
    # Convert to Europe/Dublin (Irish time)
    dublin = pytz.timezone('Europe/Dublin')
    dt_ist = dt.astimezone(dublin)
    return dt_ist

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
    return f'🏉 Match Thread: {opponent} | {date_fmt} | {time_fmt} (IST) | {comp_short} | {venue}'

def build_body(dt_ist, venue, competition, broadcasters):
    date_fmt = dt_ist.strftime('%a %d %b %Y')
    time_fmt = dt_ist.strftime('%H:%M')
    return f"""🏉 **Kickoff:** {date_fmt} @ {time_fmt} (IST)

📍 **Venue:** {venue}

🏆 **Competition:** {competition}

📺 **Broadcasters:** {broadcasters}

It’s all to play for! Drop your thoughts as the match unfolds — COME ON MUNSTER, SUAF! 🔥🔴🦌
---
*Automated by /u/MunsterKickoff 🤖*"""

def post_exists(title):
    sub = reddit.subreddit(SUBREDDIT)
    results = sub.search(f'title:"{title}"', sort='new', time_filter='year')
    return any(results)

def main():
    now = datetime.now(pytz.timezone('Europe/Dublin'))
    fixtures = scrape_fixtures()
    
    for fixture in fixtures:
        dt_ist = parse_datetime(fixture['date_str'], fixture['time_str'])
        if dt_ist <= now:
            continue  # Skip past matches
        
        post_time = dt_ist - relativedelta(hours=1)  # Post 1 hour before
        if post_time <= now < dt_ist:
            title = build_title(fixture['opponent'], dt_ist, comp_short(fixture['competition']), fixture['venue'])
            if not post_exists(title):
                body = build_body(dt_ist, fixture['venue'], fixture['competition'], fixture['broadcasters'])
                sub = reddit.subreddit(SUBREDDIT)
                sub.submit(title, selftext=body, send_replies=False)
                print(f'Posted: {title}')  # For logs

if __name__ == '__main__':
    main()
