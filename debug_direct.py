"""
اختبار مباشر للكود بدون Django - يتحقق من المنطق فقط
"""
import sys, os

# ── محاكاة format_supplier_response ──────────────────────────
def build_maps_url(supplier):
    url = supplier.get('maps_url') or supplier.get('google_maps_url', '')
    if url:
        return url
    loc = supplier.get('location', {})
    lat = loc.get('lat') if isinstance(loc, dict) else None
    lng = loc.get('lng') if isinstance(loc, dict) else None
    if lat and lng:
        return f"https://maps.google.com/?q={lat},{lng}"
    name = supplier.get('name', '')
    if name:
        import urllib.parse
        q = urllib.parse.quote(f"{name} عنيزة")
        return f"https://www.google.com/maps/search/{q}"
    return ''

def format_supplier_response(supplier):
    response = f"*{supplier.get('name', '')}*\n"
    response += f"   ⭐ {supplier.get('rating', 0)}/5\n"
    if supplier.get('phone'):
        response += f"   📞 {supplier['phone']}\n"
    address = supplier.get('address', '')
    if not address:
        loc = supplier.get('location', {})
        address = loc.get('address', '') if isinstance(loc, dict) else ''
    if address:
        response += f"   📍 {address}\n"
    if supplier.get('is_partner'):
        response += "   ✅ شريك معتمد\n"
    maps_url = build_maps_url(supplier)
    if maps_url:
        response += f"   🗺️ {maps_url}\n"
    return response.strip()

def format_search_results(results, query=""):
    db_results = results.get('database_results', [])
    google_results = results.get('google_results', [])
    if not db_results and not google_results:
        return f"ما لقيت '{query}' في عنيزة"
    response = f"🔍 هذي أحسن الخيارات لـ '{query}':\n\n"
    count = 0
    if db_results:
        for i, supplier in enumerate(db_results[:2], 1):
            response += f"{i}. {format_supplier_response(supplier)}\n\n"
            count = i
    if google_results and count < 2:
        for i, place in enumerate(google_results[:2-count], count + 1):
            response += f"{i}. {format_supplier_response(place)}\n\n"
    response += "تبي شي ثاني؟ 🐺"
    return response.strip()

# ── TEST 1: مورد عنده هاتف ورابط ───────────────────────────
print("=" * 60)
print("TEST 1: مورد عنده هاتف ورابط maps_url مباشر")
print("=" * 60)
supplier_with_data = {
    'name': 'مطعم الريم',
    'category': 'مطاعم',
    'rating': 4.5,
    'phone': '0501234567',
    'location': {'lat': 26.084, 'lng': 43.993, 'address': 'حي الصالحية، عنيزة'},
    'maps_url': 'https://maps.google.com/?q=26.084,43.993',
    'is_partner': True,
    'source': 'database'
}
out = format_supplier_response(supplier_with_data)
print(out)
print()

# ── TEST 2: مورد بدون هاتف وبدون maps_url ──────────────────
print("=" * 60)
print("TEST 2: مورد بدون هاتف وبدون maps_url - fallback بالاسم")
print("=" * 60)
supplier_no_data = {
    'name': 'مطعم الوليد',
    'category': 'مطاعم',
    'rating': 3.8,
    'phone': '',
    'location': {},
    'maps_url': '',
    'is_partner': False,
    'source': 'database'
}
out2 = format_supplier_response(supplier_no_data)
print(out2)
print()

# ── TEST 3: format_search_results كاملة ───────────────────
print("=" * 60)
print("TEST 3: format_search_results مع نتيجتين")
print("=" * 60)
out3 = format_search_results({
    'database_results': [supplier_with_data, supplier_no_data],
    'google_results': [],
    'total': 2
}, query="مطعم")
print(out3)
print()

# ── TEST 4: محاكاة phone_numbers مثل ما في DB ──────────────
print("=" * 60)
print("TEST 4: phone_numbers كـ list مثل Django model")
print("=" * 60)
# في Django، phone_numbers محفوظة كـ ArrayField
# get_primary_phone ترجع أول عنصر
class FakeSupplier:
    name_ar = "مطعم النخيل"
    name_en = ""
    phone_numbers = ["0551234567", "0509876543"]
    location = {"lat": 26.084, "lng": 43.993, "address": "طريق الملك فهد"}
    google_maps_url = ""
    rating = 4.2
    is_partner = False
    description = "مطعم شعبي"
    
    class category:
        name_ar = "مطاعم"
    
    def get_primary_phone(self):
        if self.phone_numbers and isinstance(self.phone_numbers, list):
            return self.phone_numbers[0]
        return ''

s = FakeSupplier()
result = {
    'name': s.name_ar,
    'phone': s.get_primary_phone(),
    'location': s.location,
    'maps_url': s.google_maps_url,
    'rating': s.rating,
    'is_partner': s.is_partner,
}
print(f"phone: '{result['phone']}'")
print(format_supplier_response(result))
