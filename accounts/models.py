from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('unassigned', 'Unassigned'),
        ('user', 'User'),
        ('advertiser', 'Advertiser'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='unassigned')
    profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True)

    # Email verification OTP
    otp = models.CharField(max_length=6, blank=True, null=True)
    otp_expires_at = models.DateTimeField(blank=True, null=True)

    is_email_verified = models.BooleanField(default=False)

    # Password reset OTP
    reset_password_otp = models.CharField(max_length=6, blank=True, null=True)
    reset_otp_expires_at = models.DateTimeField(blank=True, null=True)

    # Advertiser approval
    is_advertiser_approved = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.email

    def otp_is_valid(self):
        if not self.otp or not self.otp_expires_at:
            return False
        return timezone.now() <= self.otp_expires_at

    def reset_otp_is_valid(self):
        if not self.reset_password_otp or not self.reset_otp_expires_at:
            return False
        return timezone.now() <= self.reset_otp_expires_at

    def can_login_as_advertiser(self):
        """Advertiser may use advertiser features only when email verified & admin approved."""
        if self.role != "advertiser":
            return False
        return self.is_email_verified and self.is_advertiser_approved

