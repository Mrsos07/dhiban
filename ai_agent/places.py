"""
تكامل Google Maps API (New)
للبحث عن الأماكن والموردين في عنيزة
"""
import os
import json
import urllib.request
import urllib.error
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY', '')

# إحداثيات عنيزة
UNAIZAH_LOCATION = {
    "lat": 26.0844,
    "lng": 43.9936
}


def search_nearby_places(
    query: str,
    location: Optional[Dict] = None,
    radius: int = 5000,
    place_type: Optional[str] = None,
    max_results: int = 5,
    exclude_names: Optional[set] = None,
) -> List[Dict]:
    """
    البحث عن أماكن قريبة باستخدام Google Places API (New)
    
    Args:
        query: نص البحث
        location: الموقع {lat, lng} - افتراضيا عنيزة
        radius: نطاق البحث بالأمتار
        place_type: نوع المكان (restaurant, pharmacy, etc.)
        max_results: الحد الأقصى للنتائج
    
    Returns:
        قائمة الأماكن مرتبة حسب التقييم
    """
    if not GOOGLE_MAPS_API_KEY:
        logger.warning("Google Maps API key not configured")
        return []
    
    loc = location or UNAIZAH_LOCATION
    
    # بناء نص البحث
    search_query = f"{query} في عنيزة"
    
    # Google Places API (New) - Text Search
    url = "https://places.googleapis.com/v1/places:searchText"
    
    request_body = {
        "textQuery": search_query,
        "locationBias": {
            "circle": {
                "center": {
                    "latitude": loc["lat"],
                    "longitude": loc["lng"]
                },
                "radius": float(radius)
            }
        },
        "languageCode": "ar",
        "maxResultCount": max_results * 2  # نطلب أكثر للترتيب
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.currentOpeningHours,places.location,places.googleMapsUri,places.nationalPhoneNumber,places.internationalPhoneNumber,places.websiteUri,places.types,places.primaryType,places.regularOpeningHours"
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(request_body).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        places = data.get('places', [])
        
        if not places:
            logger.info(f"No places found for query: {query}")
            return []
        
        # ترتيب حسب التقييم
        sorted_places = sorted(
            places,
            key=lambda x: (x.get('rating', 0), x.get('userRatingCount', 0)),
            reverse=True
        )

        # استبعاد الأسماء التي عُرضت سابقاً (لدعم طلبات "اقترح بدائل")
        exclude_lower = {n.strip().lower() for n in (exclude_names or set())}

        results = []
        for place in sorted_places:
            if len(results) >= max_results:
                break
            display_name = place.get('displayName', {})
            name = display_name.get('text', 'غير معروف') if isinstance(display_name, dict) else str(display_name)
            if exclude_lower and name.strip().lower() in exclude_lower:
                continue
            
            location_data = place.get('location', {})
            opening_hours = place.get('currentOpeningHours', {})
            regular_hours = place.get('regularOpeningHours', {})
            
            # استخراج رقم الهاتف
            phone = place.get('nationalPhoneNumber') or place.get('internationalPhoneNumber', '')
            
            # استخراج ساعات العمل
            working_hours = {}
            if regular_hours and regular_hours.get('weekdayDescriptions'):
                working_hours = {'descriptions': regular_hours.get('weekdayDescriptions', [])}
            
            results.append({
                "place_id": place.get('id', ''),
                "name": name,
                "address": place.get('formattedAddress', 'غير متوفر'),
                "rating": place.get('rating', 0),
                "total_ratings": place.get('userRatingCount', 0),
                "location": {
                    "lat": location_data.get('latitude'),
                    "lng": location_data.get('longitude')
                },
                "is_open": opening_hours.get('openNow') if opening_hours else None,
                "maps_url": place.get('googleMapsUri', ''),
                "phone": phone,
                "website": place.get('websiteUri', ''),
                "types": place.get('types', []),
                "primary_type": place.get('primaryType', ''),
                "working_hours": working_hours,
            })
        
        return results
    
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        logger.error(f"Google Places API HTTP error {e.code}: {error_body[:200]}")
        return []
    except urllib.error.URLError as e:
        logger.error(f"Google Places API URL error: {e}")
        return []
    except Exception as e:
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
