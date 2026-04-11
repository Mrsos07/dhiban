from django.contrib import admin
from django.utils.html import format_html
from .models import Category, SubCategory, Supplier, Partner


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name_ar', 'name_en', 'icon', 'is_active', 'order')
    list_filter = ('is_active',)
    search_fields = ('name_ar', 'name_en')
    ordering = ('order', 'name_ar')


@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ('name_ar', 'category', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('name_ar', 'name_en')


SUPPLIER_FIELDSETS = (
    ('المعلومات الأساسية', {'fields': ('id', 'name_ar', 'name_en', 'description')}),
    ('التصنيف', {'fields': ('category', 'subcategory')}),
    ('الموقع والخرائط', {'fields': ('location', 'google_maps_url', 'google_maps_place_id')}),
    ('التواصل', {'fields': ('phone_numbers', 'email', 'website')}),
    ('التقييم', {'fields': ('rating', 'reviews_count')}),
    ('الحالة', {'fields': ('is_verified', 'is_active')}),
    ('ملاحظات الوكيل', {
        'fields': ('agent_notes',),
        'description': 'هذه الملاحظات يقرأها الوكيل الذكي عند اقتراح هذا المكان للمستخدم'
    }),
    ('تفاصيل إضافية', {'fields': ('working_hours', 'services', 'images'), 'classes': ('collapse',)}),
    ('التواريخ', {'fields': ('created_at', 'updated_at')}),
)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name_ar', 'category', 'subcategory', 'rating', 'reviews_count', 'phone_display', 'is_partner', 'is_verified', 'is_active', 'created_at')
    list_filter = ('category', 'subcategory', 'is_partner', 'is_verified', 'is_active')
    search_fields = ('name_ar', 'name_en', 'description', 'google_maps_place_id')
    readonly_fields = ('id', 'created_at', 'updated_at')
    ordering = ('-is_partner', '-rating', 'name_ar')
    list_per_page = 30

    fieldsets = (
        ('المعلومات الأساسية', {'fields': ('id', 'name_ar', 'name_en', 'description')}),
        ('التصنيف', {'fields': ('category', 'subcategory')}),
        ('الموقع والخرائط', {'fields': ('location', 'google_maps_url', 'google_maps_place_id')}),
        ('التواصل', {'fields': ('phone_numbers', 'email', 'website')}),
        ('التقييم', {'fields': ('rating', 'reviews_count')}),
        ('الحالة', {'fields': ('is_partner', 'is_verified', 'is_active')}),
        ('ملاحظات الوكيل', {
            'fields': ('agent_notes',),
            'description': 'هذه الملاحظات يقرأها الوكيل الذكي عند اقتراح هذا المكان للمستخدم'
        }),
        ('تفاصيل إضافية', {'fields': ('working_hours', 'services', 'images'), 'classes': ('collapse',)}),
        ('التواريخ', {'fields': ('created_at', 'updated_at')}),
    )

    def phone_display(self, obj):
        phones = obj.phone_numbers or []
        return phones[0] if phones else '—'
    phone_display.short_description = 'الهاتف'


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ('name_ar', 'category', 'subcategory', 'rating', 'reviews_count', 'phone_display', 'maps_link', 'is_active', 'created_at')
    list_filter = ('category', 'subcategory', 'is_active')
    search_fields = ('name_ar', 'name_en', 'description', 'agent_notes')
    readonly_fields = ('id', 'is_partner', 'created_at', 'updated_at')
    ordering = ('-rating', 'name_ar')
    list_per_page = 30

    fieldsets = SUPPLIER_FIELDSETS

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_partner=True)

    def save_model(self, request, obj, form, change):
        obj.is_partner = True
        super().save_model(request, obj, form, change)

    def phone_display(self, obj):
        phones = obj.phone_numbers or []
        return phones[0] if phones else '—'
    phone_display.short_description = 'الهاتف'

    def maps_link(self, obj):
        url = obj.google_maps_url or ''
        if not url and obj.location:
            lat = obj.location.get('lat')
            lng = obj.location.get('lng')
            if lat and lng:
                url = f"https://maps.google.com/?q={lat},{lng}"
        if url:
            return format_html('<a href="{}" target="_blank">🗺️ خريطة</a>', url)
        return '—'
    maps_link.short_description = 'الموقع'
