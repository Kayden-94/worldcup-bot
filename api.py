"""
API : football-data.org — gratuit, 10 req/min, Coupe du Monde incluse.
Clé gratuite sur : https://www.football-data.org/client/register
Docs : https://www.football-data.org/documentation/quickstart

Statuts possibles : SCHEDULED, TIMED, IN_PLAY, PAUSED, FINISHED,
                    SUSPENDED, POSTPONED, CANCELLED
"""

import os
import httpx
from datetime import datetime, timedelta, timezone
import time

_BASE = "https://api.football-data.org/v4"
_KEY  = os.getenv('FOOTBALL_DATA_API_KEY', '')
_COMP = "WC"   # code Coupe du Monde dans football-data.org

# Cache en mémoire : évite de re-appeler l'API si quelqu'un spam les commandes
_cache: dict = {}
_CACHE_TTL = 60  # secondes


async def _get(path, params=None):
    cache_key = path + str(sorted((params or {}).items()))
    cached = _cache.get(cache_key)
    if cached and time.time() - cached['ts'] < _CACHE_TTL:
        return cached['data']

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{_BASE}{path}",
            headers={"X-Auth-Token": _KEY},
            params=params,
        )
        r.raise_for_status()
        data = r.json()

    _cache[cache_key] = {'data': data, 'ts': time.time()}
    return data


async def get_upcoming_matches(days=10):
    today = datetime.now(timezone.utc).date()
    data = await _get(f'/competitions/{_COMP}/matches', {
        'status':   'SCHEDULED,TIMED',
        'dateFrom': today.isoformat(),
        'dateTo':   (today + timedelta(days=days)).isoformat(),
    })
    return [_normalize(m) for m in data.get('matches', [])]


async def get_recent_matches(days_back=2):
    today = datetime.now(timezone.utc).date()
    data = await _get(f'/competitions/{_COMP}/matches', {
        'dateFrom': (today - timedelta(days=days_back)).isoformat(),
        'dateTo':   today.isoformat(),
    })
    return [_normalize(m) for m in data.get('matches', [])]


def _normalize(m):
    score    = m.get('score', {})
    duration = score.get('duration', 'REGULAR')
    full     = score.get('fullTime', {})

    penalty_winner = None
    if duration == 'PENALTY_SHOOTOUT':
        # L'API met parfois le score des pénaltés dans fullTime.
        # On préfère regularTime (90 min) ou extraTime (120 min) pour le vrai score buts.
        real = score.get('regularTime') or score.get('extraTime') or full
        # score.winner indique qui a réellement gagné le match (TAB inclus)
        api_winner = score.get('winner', '')
        if api_winner == 'HOME_TEAM':
            penalty_winner = 'home'
        elif api_winner == 'AWAY_TEAM':
            penalty_winner = 'away'
    else:
        real = full

    return {
        'match_id':       str(m.get('id', '')),
        'home_team':      (m.get('homeTeam') or {}).get('shortName') or 'TBD',
        'away_team':      (m.get('awayTeam') or {}).get('shortName') or 'TBD',
        'home_score':     real.get('home'),
        'away_score':     real.get('away'),
        'match_date':     _parse_date(m.get('utcDate', '')),
        'status':         _normalize_status(m.get('status', '')),
        'penalty_winner': penalty_winner,
    }


def _parse_date(raw):
    if not raw:
        return ''
    try:
        dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    except Exception:
        return raw


def _normalize_status(s):
    s = s.upper()
    if s in ('SCHEDULED', 'TIMED'):
        return 'scheduled'
    if s in ('IN_PLAY', 'PAUSED'):
        return 'live'
    if s == 'FINISHED':
        return 'finished'
    if s in ('POSTPONED', 'CANCELLED', 'SUSPENDED'):
        return 'cancelled'
    return 'scheduled'
