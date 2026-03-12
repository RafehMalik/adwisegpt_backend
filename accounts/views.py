from rest_framework import generics, permissions, status, serializers as drf_serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth.models import User
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db import transaction

from .models import UserProfile
from .serializers import (
    RegisterSerializer,
    GoogleAuthSerializer,
    UserProfileSerializer,
    UserProfileUpdateSerializer,
    VerifyEmailSerializer,
    ResendOTPSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
)
from .utils import (
    generate_otp, 
    send_otp_email, 
    otp_expiration_time, 
    notify_admins_of_new_advertiser,
    success_response,
    error_response
)
from user.throttle import (
    RegisterThrottle, LoginThrottle, ResendOTPThrottle,
    PasswordResetThrottle, OTPConfirmThrottle, GoogleAuthThrottle,
)
# ----------------------------
# 1. Register User (Email/Pass)
# ----------------------------
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [RegisterThrottle]

    @transaction.atomic
    def perform_create(self, serializer):
        # User and Profile creation is handled by RegisterSerializer.create()
        user = serializer.save()
        profile = user.profile
        
        # Setup OTP for email verification
        otp = generate_otp()
        profile.otp = otp
        profile.otp_expires_at = otp_expiration_time()
        profile.is_email_verified = False
        profile.save()

        send_otp_email(user.email, otp, purpose="Email Verification")

        if profile.role == "advertiser":
            notify_admins_of_new_advertiser(user.email, signup_type="email")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Registration failed", 
                errors=serializer.errors, 
                status_code=status.HTTP_400_BAD_REQUEST
            )

        self.perform_create(serializer)
        return success_response(
            message="Registration successful. OTP sent to your email.",
            status_code=status.HTTP_201_CREATED
        )

# ----------------------------
# 2. Google Auth (Login/Signup)
# ----------------------------
class GoogleAuthView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [GoogleAuthThrottle]

    @transaction.atomic
    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Google authentication failed",
                errors=serializer.errors
            )

        google_data = serializer.validated_data['google_user_data']
        # Extract role from frontend request (defaults to 'user')
        role = serializer.validated_data.get('role', 'user')
        email = google_data['email']

        # Get or create user
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'first_name': google_data.get('first_name', ''),
                'last_name': google_data.get('last_name', ''),
            }
        )

        if created:
            # Create profile manually (no signals)
            profile = UserProfile.objects.create(
                user=user,
                role=role,
                is_email_verified=True # Google accounts are pre-verified
            )
            
            # Logic for Advertiser Approval
            if role == "advertiser":
                user.is_active = False 
                user.save()
                notify_admins_of_new_advertiser(email, signup_type="google")
                return success_response(
                    message="Advertiser account created successfully. Awaiting admin approval.",
                    status_code=status.HTTP_201_CREATED
                )
            
            user.is_active = True
            user.save()
        else:
            profile = user.profile

        # Logic for Inactive/Unapproved accounts
        if not user.is_active:
            if profile.role == "advertiser" and not profile.is_advertiser_approved:
                return error_response(
                    message="Your advertiser account is pending admin approval.",
                    status_code=status.HTTP_403_FORBIDDEN
                )
            return error_response(message="Your account is currently inactive.", status_code=status.HTTP_403_FORBIDDEN)

        # Generate JWT Tokens
        refresh = RefreshToken.for_user(user)
        return success_response(
            data={
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'role': profile.role,
                'email': user.email,
                'first_name': user.first_name
            },
            message="Login successful"
        )

# ----------------------------
# 3. Verify Email
# ----------------------------
class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Invalid data", errors=serializer.errors)

        email = serializer.validated_data["email"].lower()
        otp = serializer.validated_data["otp"]

        try:
            user = User.objects.get(email=email)
            profile = user.profile
        except (User.DoesNotExist, UserProfile.DoesNotExist):
            return error_response(message="User or Profile not found", status_code=status.HTTP_404_NOT_FOUND)

        if not profile.otp_is_valid() or profile.otp != otp:
            return error_response(message="Invalid or expired OTP")

        profile.is_email_verified = True
        profile.otp = None
        profile.otp_expires_at = None
        profile.save()

        # Activation Logic: User activates, Advertiser waits for Admin
        if profile.role == "user":
            user.is_active = True
            user.save()
            return success_response(message="Email verified. You can now login.")
        
        return success_response(message="Email verified. Your account is now awaiting admin approval.")

# ----------------------------
# 4. Resend OTP
# ----------------------------
class ResendOTPView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ResendOTPThrottle]

    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors)

        email = serializer.validated_data["email"].lower()
        purpose = serializer.validated_data["purpose"]

        try:
            user = User.objects.get(email=email)
            profile = user.profile
        except Exception:
            return error_response(message="Account not found", status_code=status.HTTP_404_NOT_FOUND)

        otp = generate_otp()
        if purpose == "email_verify":
            profile.otp = otp
            profile.otp_expires_at = otp_expiration_time()
        else:
            profile.reset_password_otp = otp
            profile.reset_otp_expires_at = otp_expiration_time()
        
        profile.save()
        send_otp_email(email, otp, purpose=purpose.replace('_', ' ').title())

        return success_response(message=f"{purpose.replace('_', ' ').title()} OTP resent successfully")

# ----------------------------
# 5. JWT Login (Standard)
# ----------------------------
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        
        if not self.user.is_active:
            profile = getattr(self.user, "profile", None)
            if profile and not profile.is_email_verified:
                raise drf_serializers.ValidationError("Please verify your email before logging in.")
            raise drf_serializers.ValidationError("Account is pending approval or inactive.")

        profile = self.user.profile
        data["role"] = profile.role
        data["email"] = self.user.email
        return data

class CustomLoginView(TokenObtainPairView):
    throttle_classes = [LoginThrottle]
    serializer_class = CustomTokenObtainPairSerializer

# ----------------------------
# 6. Profile View
# ----------------------------
class UserProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return UserProfileUpdateSerializer
        return UserProfileSerializer

    def get_object(self):
        return self.request.user.profile

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return success_response(data=serializer.data, message="Profile retrieved successfully")

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            return error_response(message="Update failed", errors=serializer.errors)
        
        serializer.save()
        return success_response(data=serializer.data, message="Profile updated successfully")

# ----------------------------
# 7. Password Reset Request
# ----------------------------
class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Invalid email address", errors=serializer.errors)

        email = serializer.validated_data["email"].lower()
        try:
            user = User.objects.get(email=email)
            profile = user.profile
        except Exception:
            # Consistent message even if user doesn't exist for security
            return error_response(message="If the account exists, a reset OTP has been sent.")

        otp = generate_otp()
        profile.reset_password_otp = otp
        profile.reset_otp_expires_at = otp_expiration_time()
        profile.save()

        send_otp_email(email, otp, purpose="Password Reset")
        return success_response(message="Password reset OTP sent to your email.")

# ----------------------------
# 8. Password Reset Confirm
# ----------------------------
class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(message="Validation failed", errors=serializer.errors)

        data = serializer.validated_data
        try:
            user = User.objects.get(email=data["email"].lower())
            profile = user.profile
        except Exception:
            return error_response(message="User not found")

        if not profile.reset_otp_is_valid() or profile.reset_password_otp != data["otp"]:
            return error_response(message="Invalid or expired OTP")

        user.set_password(data["new_password"])
        user.save()
        
        profile.reset_password_otp = None
        profile.reset_otp_expires_at = None
        profile.save()

        return success_response(message="Password reset successful. You can now login.")

# ----------------------------
# 9. Logout
# ----------------------------
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return error_response(message="Refresh token is required")
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return success_response(message="Logged out successfully")
        except Exception:
            return error_response(message="Invalid or expired token")
        



# ===================================================================
# DELETE USER VIEW 
# ===================================================================

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db import transaction
from django.contrib.auth.models import User
from .models import UserProfile
from .utils import success_response, error_response


class DeleteUserView(APIView):
    """
    DELETE /api/accounts/delete/
    
    Authenticated user can delete their own account.
    Permanently removes all related data from database.
    
    For Advertisers:
    - Deletes all campaigns (triggers vectorstore cleanup via signals)
    - Deletes all ad metrics (cascade)
    - Deletes all ad events (cascade)
    - Deletes subscription
    - Keeps payment history for legal/audit purposes
    
    For Regular Users:
    - Deletes user preferences
    - Deletes all chat sessions and messages
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def delete(self, request):
        user = request.user
        profile = user.profile
        user_email = user.email
        user_role = profile.role

        try:
            # Delete related data based on role
            if profile.role == "advertiser":
                deletion_summary = self._delete_advertiser_data(user)
            else:
                deletion_summary = self._delete_user_data(user)

            # Hard delete the user (this cascades to profile automatically)
            user.delete()

            return success_response(
                message="Account deleted successfully. All related data has been removed.",
                data={
                    'email': user_email,
                    'role': user_role,
                    'deleted_items': deletion_summary
                },
                status_code=status.HTTP_200_OK
            )

        except Exception as e:
            return error_response(
                message="Failed to delete account",
                errors=str(e),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _delete_advertiser_data(self, user):
        """
        Handle advertiser account deletion.
        
        Deletes:
        1. All campaigns (AdvertiserAd) - Hard delete (triggers vectorstore cleanup signal)
        2. All ad metrics (AdMetrics) - Cascade from campaigns
        3. All ad events (AdEvent) - Cascade from campaigns
        4. User subscription (UserSubscription) - Hard delete
        5. Payment history (SubscriptionPayment) - KEEP for audit/legal purposes
        """
        summary = {
            'role': 'advertiser',
            'campaigns_deleted': 0,
            'ad_metrics_deleted': 0,
            'ad_events_deleted': 0,
            'subscription_deleted': 0,
            'payments_kept': 0
        }

        try:
            from advertisers.models import (
                AdvertiserAd, 
                AdMetrics, 
                AdEvent, 
                UserSubscription,
                SubscriptionPayment
            )

            # 1. Count metrics and events before deletion (they'll cascade)
            summary['ad_metrics_deleted'] = AdMetrics.objects.filter(ad__advertiser=user).count()
            summary['ad_events_deleted'] = AdEvent.objects.filter(ad__advertiser=user).count()

            # 2. Delete campaigns - This will:
            #    - Trigger post_delete signal to remove from vectorstore
            #    - CASCADE delete AdMetrics and AdEvent
            campaigns = AdvertiserAd.objects.filter(advertiser=user)
            summary['campaigns_deleted'] = campaigns.count()
            campaigns.delete()

            # 3. Delete Subscription
            try:
                subscription = UserSubscription.objects.get(user=user)
                subscription.delete()
                summary['subscription_deleted'] = 1
            except UserSubscription.DoesNotExist:
                pass

            # 4. Keep Payment History (required for legal/accounting/audit purposes)
            summary['payments_kept'] = SubscriptionPayment.objects.filter(user=user).count()
            
            # NOTE: If you want to delete payments too (not recommended), uncomment:
            # SubscriptionPayment.objects.filter(user=user).delete()

        except Exception as e:
            raise Exception(f"Error deleting advertiser data: {str(e)}")

        return summary

    def _delete_user_data(self, user):
        """
        Handle regular user account deletion.
        
        Deletes:
        1. User preferences (UserPreference)
        2. All chat sessions (ChatSession) - Cascades to ChatMessage
        """
        summary = {
            'role': 'user',
            'preferences_deleted': 0,
            'chat_sessions_deleted': 0,
            'chat_messages_deleted': 0
        }

        try:
            from user.models import UserPreference, ChatSession, ChatMessage

            # 1. Delete User Preferences
            try:
                preference = UserPreference.objects.get(user=user)
                preference.delete()
                summary['preferences_deleted'] = 1
            except UserPreference.DoesNotExist:
                pass

            # 2. Count and delete chat data
            summary['chat_messages_deleted'] = ChatMessage.objects.filter(session__user=user).count()
            
            chat_sessions = ChatSession.objects.filter(user=user)
            summary['chat_sessions_deleted'] = chat_sessions.count()
            chat_sessions.delete()  # This cascades to ChatMessage

        except Exception as e:
            raise Exception(f"Error deleting user data: {str(e)}")

        return summary