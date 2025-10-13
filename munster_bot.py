import requests
import mwparserfromhell
from dateutil import parser
from datetime import datetime, timezone

# Wikipedia page for Munster Rugby season
SEASON_PAGE = "2025-26_Munster_Rugby_season"

def get_wikitext(title):
    """
    Fetches the wikitext of a Wikipedia page via MediaWiki API
    """
    S = requests.Session()
    URL = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "format": "json",
        "titles": title
    }

    res = S.get(url=URL, params=params)
    res.raise_for_status()
    data = res.json()

    pages = data['query']['pages']
    page = next(iter(pages.values()))
    return page['revisions'][0]['*']

def parse_rugbyboxes(wikitext):
    """
    Extract all rugbybox templates from wikitext and return a list of match dicts
    """
    wikicode = mwparserfromhell.parse(wikitext)
    boxes = wikicode.filter_templates(matches=lambda t: t.name.strip().lower().startswith("rugbybox"))
    
    matches = []
    for box in boxes:
        match = {}
        match['date'] = box.get('date').value.strip() if box.has('date') else None
        match['time'] = box.get('time').value.strip() if box.has('time') else None
        # home/away or team1/team2
        match['home'] = box.get('home').value.strip() if box.has('home') else (box.get('team1').value.strip() if box.has('team1') else None)
        match['away'] = box.get('away').value.strip() if box.has('away') else (box.get('team2').value.strip() if box.has('team2') else None)
        match['stadium'] = box.get('stadium').value.strip() if box.has('stadium') else None
        match['competition'] = None  # We'll assign later if needed
        matches.append(match)
    return matches

def filter_future_matches(matches):
    """
    Filters matches to only those in the future
    """
    upcoming = []
    now = datetime.now(timezone.utc)
    for m in matches:
        if m['date']:
            try:
                # Combine date and time if available
                dt_str = m['date'] + (' ' + m['time'] if m['time'] else '')
                dt = parser.parse(dt_str, dayfirst=True)
                # Convert naive datetime to UTC if needed
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt > now:
                    m['datetime'] = dt
                    upcoming.append(m)
            except Exception as e:
                continue
    return sorted(upcoming, key=lambda x: x['datetime'])

def main():
    print("🚀 Munster Bot Starting...")
    wikitext = get_wikitext(SEASON_PAGE)
    matches = parse_rugbyboxes(wikitext)
    upcoming = filter_future_matches(matches)
    
    if not upcoming:
        print("❌ No upcoming fixtures found.")
        return

    print(f"✅ Found {len(upcoming)} upcoming fixtures:\n")
    for m in upcoming:
        date_str = m['datetime'].strftime("%d %b %Y %H:%M")
        print(f"{date_str} | {m['home']} vs {m['away']} | Stadium: {m['stadium']}")

if __name__ == "__main__":
    main()
