"""
اختبار Google Maps API (New)
البحث عن أفضل مطاعم الشاورما في عنيزة
"""
import os
import json
import urllib.request
import urllib.parse
import urllib.error
from dotenv import load_dotenv

# تحميل المتغيرات البيئية
load_dotenv()

# إعدادات
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')
UNAIZAH_LAT = 26.0844
UNAIZAH_LNG = 43.9936
SEARCH_RADIUS = 5000  # 5 كم

def search_shawarma_restaurants():
    """البحث عن مطاعم الشاورما في عنيزة باستخدام Places API (New)"""
    
    if not GOOGLE_MAPS_API_KEY:
        print("❌ خطأ: لم يتم العثور على GOOGLE_MAPS_API_KEY في ملف .env")
        return
    
    print("🔍 البحث عن مطاعم شاورما في عنيزة...")
    print(f"📍 الإحداثيات: {UNAIZAH_LAT}, {UNAIZAH_LNG}")
    print(f"📏 نطاق البحث: {SEARCH_RADIUS/1000} كم")
    print("-" * 50)
    
    # Google Places API (New) - Text Search
    url = "https://places.googleapis.com/v1/places:searchText"
    
    # بيانات الطلب
    request_body = {
        "textQuery": "مطعم شاورما في عنيزة",
        "locationBias": {
            "circle": {
                "center": {
                    "latitude": UNAIZAH_LAT,
                    "longitude": UNAIZAH_LNG
                },
                "radius": float(SEARCH_RADIUS)
            }
        },
        "languageCode": "ar",
        "maxResultCount": 10
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.currentOpeningHours,places.location,places.googleMapsUri"
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(request_body).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        # Places API (New) يرجع النتائج في 'places' وليس 'results'
        places = data.get('places', [])
        
        if places:
            print(f"\n✅ تم العثور على {len(places)} نتيجة\n")
            
            # ترتيب حسب التقييم
            sorted_results = sorted(
                places,
                key=lambda x: (x.get('rating', 0), x.get('userRatingCount', 0)),
                reverse=True
            )
            
            print("🏆 أفضل مطاعم الشاورما في عنيزة:")
            print("=" * 50)
            
            for i, place in enumerate(sorted_results[:5], 1):
                # استخراج البيانات بتنسيق API الجديد
                display_name = place.get('displayName', {})
                name = display_name.get('text', 'غير معروف') if isinstance(display_name, dict) else str(display_name)
                rating = place.get('rating', 'N/A')
                total_ratings = place.get('userRatingCount', 0)
                address = place.get('formattedAddress', 'غير متوفر')
                
                # حالة الفتح
                opening_hours = place.get('currentOpeningHours', {})
                is_open = opening_hours.get('openNow') if opening_hours else None
                open_status = "✅ مفتوح" if is_open else ("❌ مغلق" if is_open is False else "⏰ غير محدد")
                
                print(f"\n{i}. 🍽️ {name}")
                print(f"   ⭐ التقييم: {rating}/5 ({total_ratings} تقييم)")
                print(f"   📍 العنوان: {address}")
                print(f"   🕐 الحالة: {open_status}")
                
                # رابط الخريطة
                maps_uri = place.get('googleMapsUri', '')
                if maps_uri:
                    print(f"   🗺️ الخريطة: {maps_uri}")
                else:
                    location = place.get('location', {})
                    if location:
                        lat = location.get('latitude')
                        lng = location.get('longitude')
                        print(f"   🗺️ الخريطة: https://www.google.com/maps?q={lat},{lng}")
            
            print("\n" + "=" * 50)
            print("✅ اختبار Google Maps API ناجح!")
            
        else:
            print("⚠️ لم يتم العثور على نتائج")
            print(f"البيانات المرجعة: {json.dumps(data, ensure_ascii=False, indent=2)}")
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"❌ خطأ HTTP {e.code}: {e.reason}")
        try:
            error_data = json.loads(error_body)
            print(f"الرسالة: {error_data.get('error', {}).get('message', error_body)}")
        except:
            print(f"التفاصيل: {error_body[:500]}")
        
        if e.code == 403:
            print("\nتأكد من:")
            print("  1. تفعيل Places API (New) في Google Cloud Console")
            print("  2. صحة مفتاح API")
            print("  3. عدم وجود قيود على المفتاح تمنع الوصول")
            
    except urllib.error.URLError as e:
        print(f"❌ خطأ في الاتصال: {e}")
    except Exception as e:
        print(f"❌ خطأ غير متوقع: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    search_shawarma_restaurants()
