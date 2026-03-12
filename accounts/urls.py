
from django.urls import path
from .views import (
    RegisterView, GoogleAuthView, VerifyEmailView, ResendOTPView, 
    CustomLoginView, UserProfileView, PasswordResetRequestView, PasswordResetConfirmView,DeleteUserView
)
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("google-auth/", GoogleAuthView.as_view(), name="google-auth"), # Standardized name
    path("login/", CustomLoginView.as_view(), name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("resend-otp/", ResendOTPView.as_view(), name="resend-otp"),
    path("profile/", UserProfileView.as_view(), name="profile"),
    path("password-reset/request/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path('delete/', DeleteUserView.as_view(), name='delete-account'),

]

