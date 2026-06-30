import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv('DB_PATH', 'worldcup.db')


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS matches (
            match_id       TEXT PRIMARY KEY,
            home_team      TEXT NOT NULL,
            away_team      TEXT NOT NULL,
            home_score     INTEGER,
            away_score     INTEGER,
            match_date     TEXT NOT NULL,
            status         TEXT DEFAULT 'scheduled',
            last_updated   TEXT,
            penalty_winner TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            discord_id   TEXT PRIMARY KEY,
            username     TEXT NOT NULL,
            total_points INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS predictions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id    TEXT NOT NULL,
            username      TEXT NOT NULL,
            match_id      TEXT NOT NULL,
            home_score    INTEGER NOT NULL,
            away_score    INTEGER NOT NULL,
            submitted_at  TEXT NOT NULL,
            points_earned INTEGER,
            UNIQUE(discord_id, match_id),
            FOREIGN KEY (discord_id) REFERENCES users(discord_id)
        );

        CREATE TABLE IF NOT EXISTS bot_config (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    ''')
    conn.commit()
    # Migration : ajoute la colonne si la DB existait avant cette version
    try:
        conn.execute('ALTER TABLE matches ADD COLUMN penalty_winner TEXT')
        conn.commit()
    except Exception:
        pass
    conn.close()


# ── Matches ──────────────────────────────────────────────────────────────────

def upsert_match(match_id, home_team, away_team, match_date, status,
                 home_score=None, away_score=None, penalty_winner=None, force=False):
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    if force:
        conn.execute('''
            INSERT INTO matches
                (match_id, home_team, away_team, home_score, away_score,
                 match_date, status, last_updated, penalty_winner)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                home_score     = excluded.home_score,
                away_score     = excluded.away_score,
                status         = excluded.status,
                last_updated   = excluded.last_updated,
                penalty_winner = excluded.penalty_winner
        ''', (match_id, home_team, away_team, home_score, away_score,
              match_date, status, now, penalty_winner))
    else:
        # Mise à jour API : ne pas écraser un score déjà corrigé (finished)
        conn.execute('''
            INSERT INTO matches
                (match_id, home_team, away_team, home_score, away_score,
                 match_date, status, last_updated, penalty_winner)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                home_score     = CASE WHEN matches.status = 'finished'
                                      THEN matches.home_score
                                      ELSE excluded.home_score END,
                away_score     = CASE WHEN matches.status = 'finished'
                                      THEN matches.away_score
                                      ELSE excluded.away_score END,
                penalty_winner = CASE WHEN matches.status = 'finished'
                                      THEN matches.penalty_winner
                                      ELSE excluded.penalty_winner END,
                status         = excluded.status,
                last_updated   = excluded.last_updated
        ''', (match_id, home_team, away_team, home_score, away_score,
              match_date, status, now, penalty_winner))
    conn.close()


def get_upcoming_matches(limit=10):
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    rows = conn.execute('''
        SELECT * FROM matches
        WHERE status = 'scheduled' AND match_date > ?
        ORDER BY match_date ASC
        LIMIT ?
    ''', (now, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_match(match_id):
    conn = get_connection()
    row = conn.execute(
        'SELECT * FROM matches WHERE match_id = ?', (match_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_finished_unprocessed_matches():
    conn = get_connection()
    rows = conn.execute('''
        SELECT DISTINCT m.* FROM matches m
        JOIN predictions p ON m.match_id = p.match_id
        WHERE m.status = 'finished'
          AND p.points_earned IS NULL
          AND m.home_score IS NOT NULL
          AND m.away_score IS NOT NULL
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def find_match_by_teams(home_team, away_team):
    conn = get_connection()
    row = conn.execute(
        'SELECT * FROM matches WHERE LOWER(home_team) LIKE ? AND LOWER(away_team) LIKE ?',
        (f'%{home_team.lower()}%', f'%{away_team.lower()}%')
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_matches():
    conn = get_connection()
    rows = conn.execute(
        'SELECT * FROM matches ORDER BY match_date DESC'
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def reset_predictions_for_match(match_id):
    """Soustrait les points déjà attribués et remet points_earned à NULL."""
    conn = get_connection()
    preds = conn.execute(
        'SELECT * FROM predictions WHERE match_id = ? AND points_earned IS NOT NULL',
        (match_id,)
    ).fetchall()
    conn.execute('BEGIN')
    for pred in preds:
        conn.execute(
            'UPDATE users SET total_points = MAX(0, total_points - ?) WHERE discord_id = ?',
            (pred['points_earned'], pred['discord_id'])
        )
    conn.execute(
        'UPDATE predictions SET points_earned = NULL WHERE match_id = ?',
        (match_id,)
    )
    conn.execute('COMMIT')
    conn.close()
    return len(preds)


# ── Predictions ───────────────────────────────────────────────────────────────

def upsert_prediction(discord_id, username, match_id, home_score, away_score):
    conn = get_connection()
    conn.execute('''
        INSERT INTO users (discord_id, username) VALUES (?, ?)
        ON CONFLICT(discord_id) DO UPDATE SET username = excluded.username
    ''', (discord_id, username))
    conn.execute('''
        INSERT INTO predictions
            (discord_id, username, match_id, home_score, away_score, submitted_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(discord_id, match_id) DO UPDATE SET
            home_score   = excluded.home_score,
            away_score   = excluded.away_score,
            submitted_at = excluded.submitted_at
    ''', (discord_id, username, match_id, home_score, away_score,
          datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()


def get_user_predictions(discord_id):
    conn = get_connection()
    rows = conn.execute('''
        SELECT p.*,
               m.home_team, m.away_team, m.match_date, m.status,
               m.home_score AS real_home, m.away_score AS real_away,
               m.penalty_winner
        FROM predictions p
        JOIN matches m ON p.match_id = m.match_id
        WHERE p.discord_id = ?
        ORDER BY m.match_date ASC
    ''', (discord_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_predictions_for_match(match_id):
    conn = get_connection()
    rows = conn.execute(
        'SELECT * FROM predictions WHERE match_id = ? AND points_earned IS NULL',
        (match_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_prediction_points(pred_id, points):
    conn = get_connection()
    conn.execute('UPDATE predictions SET points_earned = ? WHERE id = ?',
                 (points, pred_id))
    conn.commit()
    conn.close()


def add_user_points(discord_id, points):
    conn = get_connection()
    conn.execute(
        'UPDATE users SET total_points = total_points + ? WHERE discord_id = ?',
        (points, discord_id)
    )
    conn.commit()
    conn.close()


def set_user_points(discord_id, points):
    conn = get_connection()
    conn.execute(
        'UPDATE users SET total_points = ? WHERE discord_id = ?',
        (points, discord_id)
    )
    conn.commit()
    conn.close()


# ── Leaderboard ───────────────────────────────────────────────────────────────

def get_leaderboard(limit=10):
    conn = get_connection()
    rows = conn.execute('''
        SELECT username, total_points FROM users
        ORDER BY total_points DESC
        LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Config ────────────────────────────────────────────────────────────────────

def get_config(key):
    conn = get_connection()
    row = conn.execute(
        'SELECT value FROM bot_config WHERE key = ?', (key,)
    ).fetchone()
    conn.close()
    return row['value'] if row else None


def set_config(key, value):
    conn = get_connection()
    conn.execute('''
        INSERT INTO bot_config (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    ''', (key, value))
    conn.commit()
    conn.close()
