from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from .models import UserProfile
from django.conf import settings
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests


# -------------------------
# Register Serializer with role
# -------------------------
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)
    first_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    last_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=[("user","User"),("advertiser","Advertiser")], write_only=True)

    class Meta:
        model = User
        fields = ["email", "password", "password2", "first_name", "last_name", "role"]

    def validate_email(self, value):
        email = value.lower().strip()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("Email already registered.")
        return email

    def validate(self, attrs):
        if attrs.get("password") != attrs.get("password2"):
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        role = validated_data.pop("role")
        validated_data.pop("password2", None)

        email = validated_data.get("email").lower().strip()
        username = email  # using email as username

        # Ensure unique username 
        if User.objects.filter(username=username).exists():
            # This should be rare because email uniqueness was checked; but defensive fallback:
            username = username + "-" + str(User.objects.count() + 1)

        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            password=validated_data["password"],
            is_active=False,  
        )

        # Create profile
        UserProfile.objects.create(user=user, role=role)
        return user


# -------------------------
# Profile Serializer
# -------------------------
class UserProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", required=False, allow_blank=True)
    last_name = serializers.CharField(source="user.last_name", required=False, allow_blank=True)

    class Meta:
        model = UserProfile
        fields = [
            "email",
            "first_name",
            "last_name",
            "role",
            "profile_image",
            "is_email_verified",
            "is_advertiser_approved",
            "created_at"
        ]
        read_only_fields = ["email", "is_email_verified", "is_advertiser_approved", "created_at"]


# -------------------------
# Profile Update Serializer 
# -------------------------
class UserProfileUpdateSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source="user.first_name", required=False, allow_blank=True)
    last_name = serializers.CharField(source="user.last_name", required=False, allow_blank=True)

    class Meta:
        model = UserProfile
        fields = ["first_name", "last_name", "profile_image"]

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})
        if "first_name" in user_data:
            instance.user.first_name = user_data["first_name"]
        if "last_name" in user_data:
            instance.user.last_name = user_data["last_name"]
        instance.user.save()

        # update profile_image if provided
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


# -------------------------
# Verify Email Serializer
# -------------------------
class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)


# -------------------------
# Resend OTP Serializer 
# -------------------------
class ResendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    purpose = serializers.ChoiceField(choices=["email_verify", "password_reset"])


# -------------------------
# Forgot Password (Request)
# -------------------------
class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


# -------------------------
# Reset Password (Confirm)
# -------------------------
class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(min_length=6)

    def validate_new_password(self, value):
        validate_password(value)
        return value




from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from django.conf import settings

class GoogleAuthSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    role = serializers.ChoiceField(
        choices=[("user", "User"), ("advertiser", "Advertiser")],
        required=False,
        default="user"
    )

    def validate(self, attrs):
        token = attrs.get('token')
        google_client_id = getattr(settings, 'GOOGLE_CLIENT_ID', None)

        if not google_client_id:
            raise serializers.ValidationError("Google Client ID not configured in settings.")

        try:
            # Verify the token with Google's API
            idinfo = id_token.verify_oauth2_token(
                token, 
                google_requests.Request(), 
                google_client_id
            )

            # Check issuer
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise serializers.ValidationError("Invalid token issuer.")

            # Attach the verified data to attrs so the view can use it
            attrs['google_user_data'] = {
                'email': idinfo.get('email').lower().strip(),
                'first_name': idinfo.get('given_name', ''),
                'last_name': idinfo.get('family_name', ''),
            }
            return attrs

        except ValueError:
            raise serializers.ValidationError("The Google token is invalid or has expired.")
        except Exception as e:
            raise serializers.ValidationError(f"Authentication failed: {str(e)}")