from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import pre_save
from django.dispatch import receiver
from datetime import timedelta
from decimal import Decimal


def default_end_date():
    """Default end date = 1 day from today"""
    return timezone.now().date() + timedelta(days=1)


class SubscriptionPlan(models.Model):
    """Subscription plans with impression limits"""
    PLAN_CHOICES = [
        ("starter", "Starter"),
        ("growth", "Growth"),
        ("enterprise", "Enterprise"),
    ]

    name = models.CharField(max_length=50, choices=PLAN_CHOICES, unique=True)
    display_name = models.CharField(max_length=100)
    impression_limit = models.PositiveIntegerField(help_text="Total impressions allowed")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)  # ← ADD THIS FIELD

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.display_name} - {self.impression_limit} impressions"


class UserSubscription(models.Model):
    """User's current subscription and remaining impressions"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT)
    remaining_impressions = models.PositiveIntegerField()
    used_impressions = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.plan.display_name}"


class AdvertiserAd(models.Model):
    """Campaign/Ad model"""
    AD_TYPE_CHOICES = [
        ("banner", "Banner"),
        ("sponsored", "Sponsored Content"),
        ("video", "Video"),
        ("native", "Native"),
    ]

    CATEGORY_CHOICES = [
        ("technology", "Technology"),
        ("fashion", "Fashion"),
        ("food", "Food & Beverage"),
        ("health", "Health & Fitness"),
        ("education", "Education"),
        ("entertainment", "Entertainment"),
        ("other", "Other"),
    ]

    PAYMENT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("failed", "Failed"),
    ]

    advertiser = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="ads"
    )

    # Campaign Details
    title = models.CharField(max_length=200)
    description = models.TextField()
    ad_type = models.CharField(max_length=50, choices=AD_TYPE_CHOICES)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default="other")
    url = models.URLField()
    media_file = models.FileField(upload_to="ads_media/", blank=True, null=True)

    # Targeting
    target_keywords = models.JSONField(default=list, blank=True)

    # Duration
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(default=default_end_date)

    # Budget & Impressions
    daily_budget = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_budget = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_impressions = models.PositiveIntegerField(default=0)
    remaining_impressions = models.PositiveIntegerField(default=0)

    # Payment
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="pending"
    )

    # Status
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["advertiser", "is_active"]),
            models.Index(fields=["is_active", "start_date", "end_date"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.advertiser.username})"

    @property
    def is_within_duration(self):
        """Check if today is within campaign duration"""
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date

    @property
    def duration_days(self):
        """Calculate total campaign duration in days"""
        return (self.end_date - self.start_date).days + 1

    @property
    def is_expired(self):
        """Check if campaign has expired"""
        today = timezone.now().date()
        return today > self.end_date

    @property
    def is_live(self):
        """Check if ad should be shown to users"""
        today = timezone.now().date()
        return (
            self.is_active
            and self.payment_status == "paid"
            and self.remaining_impressions > 0
            and self.start_date <= today <= self.end_date
        )

    def deactivate_if_expired(self):
        """Deactivate ad if it has expired"""
        if self.is_expired and self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active', 'updated_at'])
            return True
        return False


@receiver(pre_save, sender=AdvertiserAd)
def auto_deactivate_expired_ads(sender, instance, **kwargs):
    """
    Signal to automatically deactivate ads when they expire.
    This runs before every save operation.
    """
    if instance.is_expired and instance.is_active:
        instance.is_active = False


class AdMetrics(models.Model):
    """Metrics for each campaign"""
    ad = models.OneToOneField(
        AdvertiserAd,
        on_delete=models.CASCADE,
        related_name="metrics"
    )
    total_impressions = models.PositiveIntegerField(default=0)
    total_clicks = models.PositiveIntegerField(default=0)
    total_conversions = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Ad Metrics"

    def __str__(self):
        return f"Metrics for {self.ad.title}"


class AdEvent(models.Model):
    """Track individual ad events"""
    EVENT_TYPE_CHOICES = [
        ("impression", "Impression"),
        ("click", "Click"),
        ("conversion", "Conversion"),
    ]

    ad = models.ForeignKey(
        AdvertiserAd,
        on_delete=models.CASCADE,
        related_name="events"
    )
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["ad", "event_type", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.event_type} - {self.ad.title}"
    
# CORRECTED SECTION - Replace this in your models.py

import uuid

class PaymentMethod(models.TextChoices):
    EASYPAISA = "EASYPAISA", "Easypaisa"  # ← Fixed: Now all UPPERCASE
    JAZZCASH = "JAZZCASH", "JazzCash"
    CARD = "CARD", "Credit / Debit Card"


class SubscriptionPayment(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE)

    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices
    )

    transaction_id = models.CharField(max_length=100, unique=True)  # ← Added unique=True
    paid_at = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=['transaction_id']),  # ← Added for faster lookups
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.payment_method} - {self.status}"