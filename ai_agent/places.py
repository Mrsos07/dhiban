"""
تكامل Google Maps API
للبحث عن الأماكن والموردين
"""
import os
import requests
import logging
from typing import List, Dict, Optional
from django.conf import settings

logger = logging.getLogger(__name__)

GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY', '')
GOOGLE_PLACES_URL = "https://maps.googleapis.com/maps/api/place"

# إحداثيات عنيزة
UNAIZAH_LOCATION = {
    "lat": 26.0844,
    "lng": 43.9932
}


def search_nearby_places(
    query: str,
    location: Optional[Dict] = None,
    radius: int = 5000,
    place_type: Optional[str] = None
) -> List[Dict]:
    """
    البحث عن أماكن قريبة باستخدام Google Places API
    
    Args:
        query: نص البحث
        location: الموقع {lat, lng} - افتراضيا عنيزة
        radius: نطاق البحث بالأمتار
        place_type: نوع المكان (restaurant, pharmacy, etc.)
    
    Returns:
        قائمة الأماكن
    """
    if not GOOGLE_MAPS_API_KEY:
        logger.warning("Google Maps API key not configured")
        return []
    
    loc = location or UNAIZAH_LOCATION
    
    params = {
        "key": GOOGLE_MAPS_API_KEY,
        "location": f"{loc['lat']},{loc['lng']}",
        "radius": radius,
        "keyword": query,
        "language": "ar"
    }
    
    if place_type:
        params["type"] = place_type
    
    try:
        response = requests.get(
            f"{GOOGLE_PLACES_URL}/nearbysearch/json",
            params=params,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") != "OK":
            logger.warning(f"Google Places API status: {data.get('status')}")
            return []
        
        results = []
        for place in data.get("results", [])[:5]:
            results.append({
                "place_id": place.get("place_id"),
                "name": place.get("name"),
                "address": place.get("vicinity", ""),
                "rating": place.get("rating", 0),
                "total_ratings": place.get("user_ratings_total", 0),
                "location": place.get("geometry", {}).get("location", {}),
                "is_open": place.get("opening_hours", {}).get("open_now"),
                "types": place.get("types", []),
            })
        
        return results
    
    except requests.RequestException as e:
        logger.error(f"Google Places API error: {e}")
        return []


def get_place_details(place_id: str) -> Optional[Dict]:
    """
    الحصول على تفاصيل مكان معين
    
    Args:
        place_id: معرف المكان من Google
    
    Returns:
        تفاصيل المكان
    """
    if not GOOGLE_MAPS_API_KEY:
        return None
    
    params = {
        "key": GOOGLE_MAPS_API_KEY,
        "place_id": place_id,
        "fields": "name,formatted_address,formatted_phone_number,website,rating,reviews,opening_hours,geometry",
        "language": "ar"
    }
    
    try:
        response = requests.get(
            f"{GOOGLE_PLACES_URL}/details/json",
            params=params,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") != "OK":
            return None
        
        result = data.get("result", {})
        return {
            "name": result.get("name"),
            "address": result.get("formatted_address"),
            "phone": result.get("formatted_phone_number"),
            "website": result.get("website"),
            "rating": result.get("rating"),
            "location": result.get("geometry", {}).get("location"),
            "hours": result.get("opening_hours", {}).get("weekday_text", []),
            "is_open": result.get("opening_hours", {}).get("open_now"),
        }
    
    except requests.RequestException as e:
        logger.error(f"Google Place Details error: {e}")
        return None


def get_directions(
    origin: Dict,
    destination: Dict,
    mode: str = "driving"
) -> Optional[Dict]:
    """
    الحصول على الاتجاهات بين نقطتين
    
    Args:
        origin: نقطة البداية {lat, lng}
        destination: نقطة الوصول {lat, lng}
        mode: وسيلة النقل (driving, walking, transit)
    
    Returns:
        معلومات الاتجاهات
    """
    if not GOOGLE_MAPS_API_KEY:
        return None
    
    params = {
        "key": GOOGLE_MAPS_API_KEY,
        "origin": f"{origin['lat']},{origin['lng']}",
        "destination": f"{destination['lat']},{destination['lng']}",
        "mode": mode,
        "language": "ar"
    }
    
    try:
        response = requests.get(
            "https://maps.googleapis.com/maps/api/directions/json",
            params=params,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") != "OK":
            return None
        
        route = data.get("routes", [{}])[0]
        leg = route.get("legs", [{}])[0]
        
        return {
            "distance": leg.get("distance", {}).get("text"),
            "duration": leg.get("duration", {}).get("text"),
            "start_address": leg.get("start_address"),
            "end_address": leg.get("end_address"),
        }
    
    except requests.RequestException as e:
        logger.error(f"Google Directions error: {e}")
        return None


def format_google_place(place: Dict) -> str:
    """تنسيق معلومات المكان من Google"""
    response = f"""
 *{place.get('name', '')}*
 العنوان: {place.get('address', 'غير متوفر')}
"""
    
    if place.get('rating'):
        response += f" التقييم: {place['rating']}/5"
        if place.get('total_ratings'):
            response += f" ({place['total_ratings']} تقييم)"
        response += "\n"
    
    if place.get('phone'):
        response += f" الهاتف: {place['phone']}\n"
    
    if place.get('is_open') is not None:
        status = "مفتوح الآن " if place['is_open'] else "مغلق الآن "
        response += f" {status}\n"
    
    return response.strip()
