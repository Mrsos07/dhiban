from django.contrib import admin
from .models import Category, SubCategory, Supplier


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


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name_ar', 'category', 'rating', 'is_partner', 'is_verified', 'is_active', 'created_at')
    list_filter = ('category', 'is_partner', 'is_verified', 'is_active')
    search_fields = ('name_ar', 'name_en', 'google_maps_place_id')
    readonly_fields = ('id', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    
    fieldsets = (
        (None, {'fields': ('id', 'name_ar', 'name_en', 'description')}),
        ('التصنيف', {'fields': ('category', 'subcategory')}),
        ('الموقع', {'fields': ('location', 'google_maps_place_id')}),
        ('التواصل', {'fields': ('phone_numbers', 'email', 'website')}),
        ('التقييم', {'fields': ('rating', 'reviews_count')}),
        ('الحالة', {'fields': ('is_partner', 'is_verified', 'is_active')}),
        ('التفاصيل', {'fields': ('working_hours', 'services', 'images')}),
        ('التواريخ', {'fields': ('created_at', 'updated_at')}),
    )
