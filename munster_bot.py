def get_munster_matches():
    """Fetch Munster fixtures from RugbyKickoff JSON API."""
    print("Fetching Munster fixtures from RugbyKickoff API...")
    matches = []
    try:
        r = requests.get("https://www.rugbykickoff.com/api/teams/munster/fixtures", timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"❌ Error fetching fixtures: {e}")
        return []

    for item in data.get("fixtures", []):
        try:
            opponent = item.get("opponent", "TBC")
            comp = item.get("competition", "Unknown Competition")
            venue = item.get("venue", "TBC")
            date_str = item.get("dateTime")
            if not date_str:
                continue

            dt_utc = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            dt_local = dt_utc.astimezone(IRISH_TZ)

            if dt_utc < datetime.utcnow().replace(tzinfo=pytz.utc):
                continue

            matches.append({
                "teams": f"Munster vs. {opponent}" if "Munster" not in opponent else f"{opponent} vs. Munster",
                "competition": comp,
                "datetime_utc": dt_utc,
                "datetime_local": dt_local,
                "venue": venue,
                "url": "https://www.rugbykickoff.com/team/munster/"
            })
        except Exception:
            continue

    print(f"✅ Found {len(matches)} future matches.")
    return matches
