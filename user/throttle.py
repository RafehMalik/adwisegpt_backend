# chat/throttles.py
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class ChatUserMinuteThrottle(UserRateThrottle):
    scope = 'chat_user'

class ChatUserDailyThrottle(UserRateThrottle):
    scope = 'chat_user_daily'

class AdsUserThrottle(UserRateThrottle):
    scope = 'ads_user'

class NewChatThrottle(UserRateThrottle):
    scope = 'new_chat'

class RefreshAdsThrottle(UserRateThrottle):
    scope = 'refresh_ads'

class ContactAnonThrottle(AnonRateThrottle):
    scope = 'contact_anon'

#advertiser throtle

class AdEventAnonThrottle(AnonRateThrottle):
    scope = 'ad_event_anon'

class AdClickAnonThrottle(AnonRateThrottle):
    scope = 'ad_click_anon'

class CampaignCreateThrottle(UserRateThrottle):
    scope = 'campaign_create'

class SubmitPaymentThrottle(UserRateThrottle):
    scope = 'submit_payment'

class AnalyticsThrottle(UserRateThrottle):
    scope = 'analytics'

class DashboardThrottle(UserRateThrottle):
    scope = 'dashboard'

# accounts throttle
class RegisterThrottle(AnonRateThrottle):
    scope = 'register'

class LoginThrottle(AnonRateThrottle):
    scope = 'login'

class ResendOTPThrottle(AnonRateThrottle):
    scope = 'resend_otp'

class PasswordResetThrottle(AnonRateThrottle):
    scope = 'password_reset'

class OTPConfirmThrottle(AnonRateThrottle):
    scope = 'otp_confirm'

class GoogleAuthThrottle(AnonRateThrottle):
    scope = 'google_auth'