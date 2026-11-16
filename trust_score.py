import math

def trust_score(
    n_ratings, avg_rating, txns,
    lost, neutral, verified_pts,
    site_avg=3.5, m=5
):
    bayes = (
        n_ratings * avg_rating + m * site_avg
    ) / (n_ratings + m)

    R = max(0, min(5, (bayes - 1) / 4 * 5))
    D = max(0, min(5, 5 * (1 - (lost + 0.25 * neutral) / (txns + 5))))
    E = max(0, min(5, 5 * (1 - math.exp(-txns / 20))))
    V = max(0, min(5, 5 * verified_pts))

    return round(
        0.45 * R + 0.30 * D + 0.15 * E + 0.10 * V,
        2,
    )
