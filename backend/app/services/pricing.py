import math

def round_to_nearest_5(amount: float) -> int:
    """Rounds amount to the nearest multiple of 5 using standard arithmetic rounding."""
    return int(math.floor((amount / 5.0) + 0.5)) * 5

def calculate_rental_suggestion(purchase_price: float, age_years: float) -> dict:
    """
    Rule-based rental pricing suggestion:
    - Current value = purchase_price * (0.85 ** age_years)
    - Daily rent = 4% of current value, rounded to the nearest ₹5
    - Refundable security deposit = 20% of current value, rounded to the nearest ₹5
    """
    purchase_price = max(0.0, float(purchase_price or 0))
    age_years = max(0.0, float(age_years or 0))

    current_value = round(purchase_price * (0.85 ** age_years), 2)
    daily_rent = float(round_to_nearest_5(current_value * 0.04))
    security_deposit = float(round_to_nearest_5(current_value * 0.20))

    return {
        "current_value": current_value,
        "daily_rent": daily_rent,
        "security_deposit": security_deposit,
        "suggested_price_per_day": daily_rent,
        "current_value_estimate": current_value,
        "daily_rate_used": 0.04,
        "explanation": (
            f"Estimated current value: ₹{current_value:,.2f} based on {age_years} years. "
            f"Daily rent (4%): ₹{daily_rent:,.0f}, Refundable deposit (20%): ₹{security_deposit:,.0f}."
        )
    }

def suggest_price_per_day(category: str = "Other", years_owned: float = 0, price_bought: float = 0) -> dict:
    return calculate_rental_suggestion(purchase_price=price_bought, age_years=years_owned)

