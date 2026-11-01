from app.database import engine, Base, SessionLocal
from app.models import User, Listing, ListingStatus, BorrowRequest, BorrowRequestStatus
from app.services.auth import hash_password

def seed():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    # Users
    alice = User(
        name="Alice",
        username="alice",
        email="alice@example.com",
        password_hash=hash_password("password123"),
        trust_score=78.0,
    )
    bob = User(
        name="Bob",
        username="bob",
        email="bob@example.com",
        password_hash=hash_password("password123"),
        trust_score=65.0,
    )
    admin = User(
        name="Admin",
        username="admin",
        email="admin@example.com",
        password_hash=hash_password("admin123"),
        is_admin=True
    )
    db.add_all([alice, bob, admin])
    db.commit()
    
    # Listings for Alice
    listings_data = [
        {"name": "Power Drill", "category": "Drill", "price_bought": 2500, "years_owned": 2, "price_per_day": 150, "latitude": 28.6304, "longitude": 77.2177, "address_text": "Connaught Place, New Delhi"},
        {"name": "Mountain Bicycle", "category": "Bicycle", "price_bought": 15000, "years_owned": 1, "price_per_day": 200, "latitude": 28.6514, "longitude": 77.1907, "address_text": "Karol Bagh, New Delhi"},
        {"name": "Harry Potter Collection", "category": "Book", "price_bought": 1500, "years_owned": 3, "price_per_day": 50, "latitude": 28.5494, "longitude": 77.2001, "address_text": "Hauz Khas, New Delhi"},
        {"name": "Extension Ladder", "category": "Ladder", "price_bought": 8000, "years_owned": 4, "price_per_day": 120, "latitude": 28.5293, "longitude": 77.1528, "address_text": "Vasant Kunj, New Delhi"},
        {"name": "Sony Headphones", "category": "Headphones", "price_bought": 5000, "years_owned": 1, "price_per_day": 100, "latitude": 28.5244, "longitude": 77.2188, "address_text": "Saket, New Delhi"},
        {"name": "Claw Hammer", "category": "Hammer", "price_bought": 800, "years_owned": 2, "price_per_day": 30, "latitude": 28.6415, "longitude": 77.1209, "address_text": "Rajouri Garden, New Delhi"},
        {"name": "4-Person Camping Tent", "category": "Tent & Camping Gear", "price_bought": 6000, "years_owned": 1, "price_per_day": 250, "latitude": 28.6280, "longitude": 77.3649, "address_text": "Sector 62, Noida"}
    ]
    
    for data in listings_data:
        listing = Listing(
            owner_id=alice.id,
            name=data["name"],
            category=data["category"],
            price_bought=data["price_bought"],
            years_owned=data["years_owned"],
            price_per_day=data["price_per_day"],
            latitude=data["latitude"],
            longitude=data["longitude"],
            address_text=data["address_text"],
            status=ListingStatus.published
        )
        db.add(listing)
        
    # Sample Borrow Requests for Bob
    requests_data = [
        {"title": "Need a Pressure Washer for 1 day", "category": "Other", "description": "Need to clean driveway this weekend.", "max_price_per_day": 300},
        {"title": "Looking for Acoustic Guitar", "category": "Musical Instrument", "description": "For a weekend jam session with friends.", "max_price_per_day": 150},
        {"title": "Searching for Heavy Duty Lawn Mower", "category": "Other", "description": "Front yard overgrown, need for 3 hours.", "max_price_per_day": 200},
    ]

    for req in requests_data:
        br = BorrowRequest(
            borrower_id=bob.id,
            title=req["title"],
            category=req["category"],
            description=req["description"],
            max_price_per_day=req["max_price_per_day"],
            latitude=28.6139,
            longitude=77.2090,
            status=BorrowRequestStatus.open
        )
        db.add(br)

    db.commit()
    db.close()
    print("Seed complete with listings and borrow requests!")

if __name__ == "__main__":
    seed()
