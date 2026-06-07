def calculate_points(pred_home, pred_away, real_home, real_away):
    """
    3 pts → score exact
    2 pts → bonne différence de buts (mais pas le score exact)
    1 pt  → bonne équipe gagnante (mais pas la différence)
    0 pt  → rien de juste
    """
    if pred_home == real_home and pred_away == real_away:
        return 3
    if (pred_home - pred_away) == (real_home - real_away):
        return 2
    if _winner(pred_home, pred_away) == _winner(real_home, real_away):
        return 1
    return 0


def _winner(home, away):
    if home > away:
        return 'home'
    if away > home:
        return 'away'
    return 'draw'
