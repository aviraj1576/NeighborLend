import math
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Listing, ListingPhoto, ListingStatus
from app.schemas.listing import ListingCreateIn, ListingUpdateIn, ListingOut, SuggestPriceIn, SuggestPriceOut
from app.services.auth import get_current_user
from app.services.pricing import suggest_price_per_day, calculate_rental_suggestion

router = APIRouter()

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def _format_listing_out(listing: Listing, distance_km: Optional[float] = None) -> dict:
    address_str = listing.address_text or ""
    if not address_str and listing.latitude is not None and listing.longitude is not None:
        address_str = f"Location ({listing.latitude:.4f}°, {listing.longitude:.4f}°)"

    owner_dict = None
    if listing.owner:
        owner_dict = {
            "id": listing.owner.id,
            "name": listing.owner.name,
            "username": listing.owner.username,
            "trust_score": listing.owner.trust_score,
            "rating": listing.owner.avg_rating,
            "rating_count": listing.owner.rating_count
        }

    return {
        "id": listing.id,
        "owner_id": listing.owner_id,
        "owner_name": listing.owner.name if listing.owner else "Unknown",
        "owner_username": listing.owner.username if listing.owner else "Unknown",
        "owner": owner_dict,
        "owner_trust_score": listing.owner.trust_score if listing.owner else 50.0,
        "owner_avg_rating": listing.owner.avg_rating if listing.owner else 0.0,
        "owner_rating_count": listing.owner.rating_count if listing.owner else 0,
        "name": listing.name,
        "title": listing.name,
        "category": listing.category,
        "description": listing.description,
        "years_owned": listing.years_owned,
        "price_bought": listing.price_bought,
        "price_per_day": listing.price_per_day,
        "security_deposit": listing.security_deposit,
        "lending_radius_km": listing.lending_radius_km,
        "latitude": listing.latitude,
        "longitude": listing.longitude,
        "address_text": listing.address_text or "",
        "address": address_str,
        "status": listing.status,
        "moderation_reason": listing.moderation_reason,
        "ai_label": listing.ai_label,
        "ai_confidence": listing.ai_confidence,
        "photos": [
            photo.url for photo in sorted(
                listing.photos,
                key=lambda photo: (not photo.is_cover, photo.created_at, photo.id),
            )
        ],
        "is_currently_rented": False,
        "distance_km": None if distance_km == float('inf') else distance_km,
        "created_at": listing.created_at
    }

@router.post("", response_model=ListingOut)
@router.post("/", response_model=ListingOut)
def create_listing(data: ListingCreateIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    listing = Listing(
        owner_id=current_user.id,
        name=data.name,
        category=data.category,
        description=data.description,
        years_owned=data.years_owned,
        price_bought=data.price_bought,
        price_per_day=data.price_per_day,
        min_price_per_day=data.min_price_per_day,
        security_deposit=data.security_deposit,
        lending_radius_km=data.lending_radius_km,
        latitude=data.latitude,
        longitude=data.longitude,
        address_text=data.address_text,
        status=ListingStatus.published,
        ai_label=data.ai_label,
        ai_confidence=data.ai_confidence
    )
    db.add(listing)
    db.flush()
    
    for i, url in enumerate(data.photo_urls):
        photo = ListingPhoto(listing_id=listing.id, url=url, is_cover=(i==0))
        db.add(photo)
        
    db.commit()
    db.refresh(listing)
    return _format_listing_out(listing)

@router.get("", response_model=List[ListingOut])
@router.get("/", response_model=List[ListingOut])
def list_my_listings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    listings = db.query(Listing).filter(Listing.owner_id == current_user.id, Listing.status != ListingStatus.removed).all()
    return [_format_listing_out(l) for l in listings]

@router.get("/detect-location")
def detect_location(request: Request):
    """
    Attempts to detect location based on client IP or falls back to default coordinates.
    """
    import urllib.request
    import json

    client_ip = request.client.host if request.client else ""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    try:
        url = f"https://ipapi.co/{client_ip}/json/" if client_ip and client_ip not in ("127.0.0.1", "::1", "localhost") else "https://ipapi.co/json/"
        req = urllib.request.Request(url, headers={"User-Agent": "NeighborLend/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "latitude" in data and "longitude" in data:
                city = data.get("city") or "Local Area"
                region = data.get("region") or ""
                loc_name = f"{city}, {region}".strip(", ")
                return {
                    "latitude": float(data["latitude"]),
                    "longitude": float(data["longitude"]),
                    "city": city,
                    "region": region,
                    "address": loc_name or "Detected Location",
                    "source": "ip"
                }
    except Exception:
        pass

    return {
        "latitude": 28.6139,
        "longitude": 77.2090,
        "city": "New Delhi",
        "region": "Delhi",
        "address": "New Delhi, Delhi",
        "source": "default"
    }

@router.get("/search", response_model=List[ListingOut])
def search_listings(
    lat: Optional[float] = Query(None, description="Latitude for search center"),
    lon: Optional[float] = Query(None, description="Longitude for search center"),
    radius_km: Optional[float] = Query(None, description="Search radius in km. If null or >= 500, all distances included"),
    category: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Listing).filter(Listing.status == ListingStatus.published)
    if category and category != "All":
        query = query.filter(Listing.category == category)
    if q:
        query = query.filter(Listing.name.ilike(f"%{q}%"))
        
    all_listings = query.all()
    results = []
    has_coords = lat is not None and lon is not None
    is_unlimited = radius_km is None or radius_km <= 0 or radius_km >= 500

    for l in all_listings:
        if has_coords and l.latitude is not None and l.longitude is not None:
            dist = haversine(lat, lon, l.latitude, l.longitude)
            if is_unlimited or dist <= radius_km:
                results.append((dist, l))
        elif is_unlimited or not has_coords:
            # Include items without location at the end of the results
            results.append((float('inf'), l))
                
    results.sort(key=lambda x: x[0])
    return [_format_listing_out(l, dist) for dist, l in results]


@router.get("/{listing_id}", response_model=ListingOut)
def get_listing(listing_id: str, db: Session = Depends(get_db)):
    listing = db.query(Listing).filter(Listing.id == listing_id, Listing.status != ListingStatus.removed).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return _format_listing_out(listing)

@router.patch("/{listing_id}", response_model=ListingOut)
def update_listing(listing_id: str, data: ListingUpdateIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    listing = db.query(Listing).filter(Listing.id == listing_id, Listing.owner_id == current_user.id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found or unauthorized")
        
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(listing, key, value)
        
    db.commit()
    db.refresh(listing)
    return _format_listing_out(listing)

@router.delete("/{listing_id}")
def delete_listing(listing_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    listing = db.query(Listing).filter(Listing.id == listing_id, Listing.owner_id == current_user.id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found or unauthorized")
        
    listing.status = ListingStatus.removed
    db.commit()
    return {"status": "ok"}

@router.post("/suggest-price", response_model=SuggestPriceOut)
def suggest_price(data: SuggestPriceIn):
    return calculate_rental_suggestion(
        purchase_price=data.get_purchase_price(),
        age_years=data.get_age_years()
    )
