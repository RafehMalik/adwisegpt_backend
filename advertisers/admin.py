# from django.contrib import admin
# from .models import SubscriptionPlan, UserSubscription, AdvertiserAd, AdMetrics, AdEvent #,Payment


# @admin.register(SubscriptionPlan)
# class SubscriptionPlanAdmin(admin.ModelAdmin):
#     list_display = ["display_name", "name", "impression_limit", "price", "created_at"]
#     list_filter = ["name"]
#     search_fields = ["display_name", "name"]


# @admin.register(UserSubscription)
# class UserSubscriptionAdmin(admin.ModelAdmin):
#     list_display = [
#         "user",
#         "plan",
#         "remaining_impressions",
#         "used_impressions",
#         "is_active",
#         "created_at"
#     ]
#     list_filter = ["is_active", "plan"]
#     search_fields = ["user__username", "user__email"]
#     readonly_fields = ["created_at", "updated_at"]


# @admin.register(AdvertiserAd)
# class AdvertiserAdAdmin(admin.ModelAdmin):
#     list_display = [
#         "id",
#         "title",
#         "advertiser",
#         "ad_type",
#         "total_budget",
#         "remaining_impressions",
#         "is_active",
#         "payment_status",
#         "created_at"
#     ]
#     list_filter = ["ad_type", "category", "is_active", "payment_status"]
#     search_fields = ["title", "advertiser__username"]
#     readonly_fields = ["created_at", "updated_at"]
    
#     fieldsets = (
#         ("Campaign Info", {
#             "fields": ("advertiser", "title", "description", "ad_type", "category")
#         }),
#         ("Content", {
#             "fields": ("url", "media_file", "target_keywords")
#         }),
#         ("Schedule", {
#             "fields": ("start_date", "end_date")
#         }),
#         ("Budget & Impressions", {
#             "fields": (
#                 "daily_budget",
#                 "total_budget",
#                 "total_impressions",
#                 "remaining_impressions"
#             )
#         }),
#         ("Status", {
#             "fields": ("is_active", "payment_status")
#         }),
#         ("Timestamps", {
#             "fields": ("created_at", "updated_at")
#         }),
#     )


# @admin.register(AdMetrics)
# class AdMetricsAdmin(admin.ModelAdmin):
#     list_display = [
#         "ad",
#         "total_impressions",
#         "total_clicks",
#         "total_conversions",
#         "total_spent",
#         "updated_at"
#     ]
#     search_fields = ["ad__title", "ad__advertiser__username"]
#     readonly_fields = ["updated_at"]


# @admin.register(AdEvent)
# class AdEventAdmin(admin.ModelAdmin):
#     list_display = ["id", "ad", "event_type", "timestamp"]
#     list_filter = ["event_type", "timestamp"]
#     search_fields = ["ad__title"]
#     readonly_fields = ["ad", "event_type", "timestamp"]
    
#     def has_add_permission(self, request):
#         return False
    
#     def has_change_permission(self, request, obj=None):
#         return False


# # admin.py or management command
# # This shows the logic needed when admin approves a payment

# from django.db import transaction
# from django.utils import timezone
# from datetime import timedelta
# from .models import SubscriptionPayment, UserSubscription


# def approve_payment(payment_id):
#     """
#     Called when admin approves a payment.
#     This creates/updates the user's subscription.
#     """
#     with transaction.atomic():
#         # Get payment with lock
#         payment = SubscriptionPayment.objects.select_for_update().get(
#             id=payment_id,
#             status=SubscriptionPayment.STATUS_PENDING
#         )
        
#         # Update payment status
#         payment.status = SubscriptionPayment.STATUS_APPROVED
#         payment.save(update_fields=['status'])
        
#         # Get or create subscription for user
#         subscription, created = UserSubscription.objects.get_or_create(
#             user=payment.user,
#             defaults={
#                 'plan': payment.plan,
#                 'remaining_impressions': payment.plan.impression_limit,
#                 'used_impressions': 0,
#                 'is_active': True,
#                 'expires_at': timezone.now() + timedelta(days=30)  # 30 day subscription
#             }
#         )
        
#         # If subscription already exists, update it
#         if not created:
#             subscription.plan = payment.plan
#             subscription.remaining_impressions = payment.plan.impression_limit
#             subscription.used_impressions = 0
#             subscription.is_active = True
#             subscription.expires_at = timezone.now() + timedelta(days=30)
#             subscription.save()
        
#         return subscription


# def reject_payment(payment_id, reason=""):
#     """
#     Called when admin rejects a payment.
#     """
#     payment = SubscriptionPayment.objects.get(id=payment_id)
#     payment.status = SubscriptionPayment.STATUS_REJECTED
#     payment.save(update_fields=['status'])
    
#     # Optional: Send email notification to user about rejection
#     # send_rejection_email(payment.user, reason)
    
#     return payment


# # Example Django Admin Integration
# from django.contrib import admin
# from .models import SubscriptionPayment

# @admin.register(SubscriptionPayment)
# class SubscriptionPaymentAdmin(admin.ModelAdmin):
#     list_display = [
#         'user', 'plan', 'payment_method', 
#         'transaction_id', 'status', 'created_at'
#     ]
#     list_filter = ['status', 'payment_method', 'created_at']
#     search_fields = ['user__email', 'transaction_id']
#     readonly_fields = ['id', 'created_at']
    
#     actions = ['approve_payments', 'reject_payments']
    
#     def approve_payments(self, request, queryset):
#         """Bulk approve payments"""
#         approved_count = 0
#         for payment in queryset.filter(status=SubscriptionPayment.STATUS_PENDING):
#             try:
#                 approve_payment(payment.id)
#                 approved_count += 1
#             except Exception as e:
#                 self.message_user(
#                     request,
#                     f"Failed to approve payment {payment.id}: {str(e)}",
#                     level='ERROR'
#                 )
        
#         self.message_user(
#             request,
#             f"Successfully approved {approved_count} payment(s)",
#             level='SUCCESS'
#         )
    
#     approve_payments.short_description = "Approve selected payments"
    
#     def reject_payments(self, request, queryset):
#         """Bulk reject payments"""
#         rejected_count = queryset.filter(
#             status=SubscriptionPayment.STATUS_PENDING
#         ).update(status=SubscriptionPayment.STATUS_REJECTED)
        
#         self.message_user(
#             request,
#             f"Rejected {rejected_count} payment(s)",
#             level='SUCCESS'
#         )
    
#     reject_payments.short_description = "Reject selected payments"
from django.contrib import admin
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from .models import (
    SubscriptionPlan, UserSubscription, AdvertiserAd,
    AdMetrics, AdEvent, SubscriptionPayment
)


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ["display_name", "name", "impression_limit", "price", "created_at"]
    list_filter = ["name"]
    search_fields = ["display_name", "name"]


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ["user", "plan", "remaining_impressions", "used_impressions", "is_active", "created_at"]
    list_filter = ["is_active", "plan"]
    search_fields = ["user__username", "user__email"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(AdvertiserAd)
class AdvertiserAdAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "advertiser", "ad_type", "total_budget", "remaining_impressions", "is_active", "payment_status", "created_at"]
    list_filter = ["ad_type", "category", "is_active", "payment_status"]
    search_fields = ["title", "advertiser__username"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        ("Campaign Info", {"fields": ("advertiser", "title", "description", "ad_type", "category")}),
        ("Content", {"fields": ("url", "media_file", "target_keywords")}),
        ("Schedule", {"fields": ("start_date", "end_date")}),
        ("Budget & Impressions", {"fields": ("daily_budget", "total_budget", "total_impressions", "remaining_impressions")}),
        ("Status", {"fields": ("is_active", "payment_status")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(AdMetrics)
class AdMetricsAdmin(admin.ModelAdmin):
    list_display = ["ad", "total_impressions", "total_clicks", "total_conversions", "total_spent", "updated_at"]
    search_fields = ["ad__title", "ad__advertiser__username"]
    readonly_fields = ["updated_at"]


@admin.register(AdEvent)
class AdEventAdmin(admin.ModelAdmin):
    list_display = ["id", "ad", "event_type", "timestamp"]
    list_filter = ["event_type", "timestamp"]
    search_fields = ["ad__title"]
    readonly_fields = ["ad", "event_type", "timestamp"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ==================== PAYMENT HELPERS ====================

def approve_payment(payment_id):
    with transaction.atomic():
        payment = SubscriptionPayment.objects.select_for_update().get(
            id=payment_id, status=SubscriptionPayment.STATUS_PENDING
        )
        payment.status = SubscriptionPayment.STATUS_APPROVED
        payment.save(update_fields=['status'])

        subscription, created = UserSubscription.objects.get_or_create(
            user=payment.user,
            defaults={
                'plan': payment.plan,
                'remaining_impressions': payment.plan.impression_limit,
                'used_impressions': 0,
                'is_active': True,
                'expires_at': timezone.now() + timedelta(days=30)
            }
        )

        if not created:
            subscription.plan = payment.plan
            subscription.remaining_impressions = payment.plan.impression_limit
            subscription.used_impressions = 0
            subscription.is_active = True
            subscription.expires_at = timezone.now() + timedelta(days=30)
            subscription.save()

        return subscription


def reject_payment(payment_id):
    payment = SubscriptionPayment.objects.get(id=payment_id)
    payment.status = SubscriptionPayment.STATUS_REJECTED
    payment.save(update_fields=['status'])
    return payment


# ==================== PAYMENT ADMIN ====================

@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = ['user', 'plan', 'payment_method', 'transaction_id', 'status', 'created_at']
    list_filter = ['status', 'payment_method', 'created_at']
    search_fields = ['user__email', 'transaction_id']
    readonly_fields = ['id', 'created_at']
    actions = ['approve_payments', 'reject_payments']

    def approve_payments(self, request, queryset):
        approved_count = 0
        for payment in queryset.filter(status=SubscriptionPayment.STATUS_PENDING):
            try:
                approve_payment(payment.id)
                approved_count += 1
            except Exception as e:
                self.message_user(request, f"Failed to approve payment {payment.id}: {str(e)}", level='ERROR')
        self.message_user(request, f"Successfully approved {approved_count} payment(s)", level='SUCCESS')

    approve_payments.short_description = "Approve selected payments"

    def reject_payments(self, request, queryset):
        rejected_count = queryset.filter(
            status=SubscriptionPayment.STATUS_PENDING
        ).update(status=SubscriptionPayment.STATUS_REJECTED)
        self.message_user(request, f"Rejected {rejected_count} payment(s)", level='SUCCESS')

    reject_payments.short_description = "Reject selected payments"