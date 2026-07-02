def calculate_points(pred_home, pred_away, real_home, real_away, penalty_winner=None):
    """
    3 pts → score exact
    2 pts → chaque score à 1 but près (|pred_home - real_home| <= 1 ET |pred_away - real_away| <= 1)
    1 pt  → bonne équipe gagnante (y compris vainqueur aux TAB)
    0 pt  → rien de juste
    """
    if pred_home == real_home and pred_away == real_away:
        return 3
    if abs(pred_home - real_home) <= 1 and abs(pred_away - real_away) <= 1:
        return 2
    # Pour les matchs aux TAB, le vainqueur réel est celui qui a gagné les pénaltés,
    # pas le résultat du score (qui est un nul).
    actual_winner = penalty_winner if penalty_winner else _winner(real_home, real_away)
    if _winner(pred_home, pred_away) == actual_winner:
        return 1
    return 0


def _winner(home, away):
    if home > away:
        return 'home'
    if away > home:
        return 'away'
    return 'draw'
