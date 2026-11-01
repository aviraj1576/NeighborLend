import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from app.main import app
from app.services.pricing import calculate_rental_suggestion, round_to_nearest_5
from app.database import SessionLocal
from app.models import Listing

class TestSuggestPrice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_round_to_nearest_5(self):
        self.assertEqual(round_to_nearest_5(0), 0)
        self.assertEqual(round_to_nearest_5(1), 0)
        self.assertEqual(round_to_nearest_5(2), 0)
        self.assertEqual(round_to_nearest_5(2.5), 5)
        self.assertEqual(round_to_nearest_5(3), 5)
        self.assertEqual(round_to_nearest_5(4), 5)
        self.assertEqual(round_to_nearest_5(7.4), 5)
        self.assertEqual(round_to_nearest_5(7.5), 10)
        self.assertEqual(round_to_nearest_5(34), 35)
        self.assertEqual(round_to_nearest_5(170), 170)
        self.assertEqual(round_to_nearest_5(289), 290)

    def test_calculate_rental_suggestion_formula(self):
        # Test case 1: Purchase price 1000, age 1
        # Current value = 1000 * (0.85 ** 1) = 850
        # Daily rent = 850 * 0.04 = 34 -> nearest 5 = 35
        # Security deposit = 850 * 0.20 = 170 -> nearest 5 = 170
        res1 = calculate_rental_suggestion(purchase_price=1000, age_years=1)
        self.assertEqual(res1["current_value"], 850.0)
        self.assertEqual(res1["daily_rent"], 35.0)
        self.assertEqual(res1["security_deposit"], 170.0)

        # Test case 2: Purchase price 10000, age 2
        # Current value = 10000 * (0.85 ** 2) = 7225.0
        # Daily rent = 7225 * 0.04 = 289 -> nearest 5 = 290
        # Security deposit = 7225 * 0.20 = 1445 -> nearest 5 = 1445
        res2 = calculate_rental_suggestion(purchase_price=10000, age_years=2)
        self.assertEqual(res2["current_value"], 7225.0)
        self.assertEqual(res2["daily_rent"], 290.0)
        self.assertEqual(res2["security_deposit"], 1445.0)

        # Test case 3: Age 0 (brand new item)
        res3 = calculate_rental_suggestion(purchase_price=5000, age_years=0)
        self.assertEqual(res3["current_value"], 5000.0)
        self.assertEqual(res3["daily_rent"], 200.0)
        self.assertEqual(res3["security_deposit"], 1000.0)

    def test_suggest_price_api_endpoint(self):
        # Test API endpoint POST /api/listings/suggest-price
        response = self.client.post(
            "/api/listings/suggest-price",
            json={"purchase_price": 10000, "age_years": 2}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["current_value"], 7225.0)
        self.assertEqual(data["daily_rent"], 290.0)
        self.assertEqual(data["security_deposit"], 1445.0)

        # Test with alternative field aliases
        response_alt = self.client.post(
            "/api/listings/suggest-price",
            json={"original_price": 1000, "item_age": 1}
        )
        self.assertEqual(response_alt.status_code, 200)
        data_alt = response_alt.json()
        self.assertEqual(data_alt["current_value"], 850.0)
        self.assertEqual(data_alt["daily_rent"], 35.0)
        self.assertEqual(data_alt["security_deposit"], 170.0)

    def test_ephemeral_nature_no_database_write(self):
        db = SessionLocal()
        count_before = db.query(Listing).count()

        # Calling suggest-price must NOT create any listing or DB records
        self.client.post(
            "/api/listings/suggest-price",
            json={"purchase_price": 25000, "age_years": 3}
        )

        count_after = db.query(Listing).count()
        db.close()
        self.assertEqual(count_before, count_after)

    def test_detect_location_endpoint(self):
        response = self.client.get("/api/listings/detect-location")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("latitude", data)
        self.assertIn("longitude", data)
        self.assertIn("address", data)

    def test_search_listings_distance_filter(self):
        # Center in New Delhi (where seed items are)
        res_delhi = self.client.get("/api/listings/search?lat=28.6139&lon=77.2090&radius_km=50")
        self.assertEqual(res_delhi.status_code, 200)
        items = res_delhi.json()
        self.assertIsInstance(items, list)
        if len(items) > 1:
            # Check sorted by distance ascending
            for i in range(len(items) - 1):
                if items[i].get("distance_km") is not None and items[i+1].get("distance_km") is not None:
                    self.assertLessEqual(items[i]["distance_km"], items[i+1]["distance_km"])

        # Test search with unlimited / large radius
        res_all = self.client.get("/api/listings/search?lat=30.3362&lon=76.3922&radius_km=9999")
        self.assertEqual(res_all.status_code, 200)
        items_all = res_all.json()
        self.assertGreaterEqual(len(items_all), len(items))

if __name__ == "__main__":
    unittest.main()

