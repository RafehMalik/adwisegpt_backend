import random
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from rest_framework.response import Response
from rest_framework import status


OTP_TTL_MINUTES = 20  # OTP validity in minutes

def generate_otp():
    return f"{random.randint(100000, 999999):06d}"

def send_otp_email(to_email: str, otp: str, purpose: str = "Verification"):
    subject = f"{purpose} - AdWiseGPT"
    message = f"Your OTP for {purpose.lower()} is: {otp}\nIt will expire in {OTP_TTL_MINUTES} minutes."
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "EMAIL_HOST_USER", None) or 'noreply@adwisegpt.local'
    send_mail(subject, message, from_email, [to_email], fail_silently=False)

def otp_expiration_time():
    return timezone.now() + timezone.timedelta(minutes=OTP_TTL_MINUTES)

def notify_admins_of_new_advertiser(user_email: str, signup_type: str = "email"):
    """
    Send a short email to admins to notify that an advertiser signed up.
    signup_type: 'email' or 'google'
    """
    from django.conf import settings
    admin_emails = []
    admins = getattr(settings, "ADMINS", None)
    if admins:
        # ADMINS is list of (name, email) tuples
        admin_emails = [a[1] for a in admins if len(a) >= 2 and a[1]]
    # fallback to EMAIL_HOST_USER if ADMINS not configured
    if not admin_emails:
        email_host_user = getattr(settings, "EMAIL_HOST_USER", None)
        if email_host_user:
            admin_emails = [email_host_user]

    if not admin_emails:
        return

    subject = f"New advertiser signup ({signup_type}) - {user_email}"
    message = (
        f"An advertiser account has been created with email: {user_email}\n\n"
        f"Signup type: {signup_type}\n\n"
        "Please review and approve the account in the admin panel: /admin/accounts/userprofile/"
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "EMAIL_HOST_USER", None) or 'noreply@adwisegpt.local'
    send_mail(subject, message, from_email, admin_emails, fail_silently=True)




# ==================== RESPONSE HELPERS ====================

def success_response(data=None, message="Success", status_code=status.HTTP_200_OK):
    """Standard success response"""
    response_data = {
        "success": True,
        "message": message
    }
    
    if data is not None:
        response_data["data"] = data
    
    return Response(response_data, status=status_code)


def error_response(message="Something went wrong", errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    """Standard error response"""
    response_data = {
        "success": False,
        "message": message
    }
    
    if errors is not None:
        response_data["errors"] = errors
    
    return Response(response_data, status=status_code)
