from django.contrib import admin
from .models import UserProfile

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'is_email_verified', 'is_advertiser_approved', 'created_at')
    search_fields = ('user__email', 'user__username')
    list_filter = ('role', 'is_email_verified', 'is_advertiser_approved')
