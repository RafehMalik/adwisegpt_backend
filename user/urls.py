
from django.urls import path
from .views import (
    UserPreferenceView,
    ContactUsView,
    TestAdRetrievalView,
    ChatView,
    ChatAdsView,
    SessionListView,
    SessionDetailView,
    NewChatView,
    RefreshAdsView,
)

urlpatterns = [
    # Preferences & contact
    path("preferences/", UserPreferenceView.as_view(), name="user-preferences-api"),
    path("contact-us/", ContactUsView.as_view(), name="contact-us"),

    # Debug / test
    path('test-retrieval/', TestAdRetrievalView.as_view(), name='test-ad-retrieval'),

    # -----------------------------------------------------------------------
    # CHAT  (pure LLM — no ads)
    # POST  { message, session_id }
    # ← { session_id, messages }
    # -----------------------------------------------------------------------
    path('chat/', ChatView.as_view(), name='chat'),

    # -----------------------------------------------------------------------
    # ADS   (pure ad logic — no LLM call)
    # POST  { session_id, message, force_refresh? }
    # ← { session_id, sponsored_ads, ads_refreshed, refresh_reason }
    # -----------------------------------------------------------------------
    path('chat/ads/', ChatAdsView.as_view(), name='chat-ads'),

    # Session management
    path('chat/sessions/', SessionListView.as_view(), name='session-list'),
    path('chat/sessions/<str:session_id>/', SessionDetailView.as_view(), name='session-detail'),
    path('chat/new/', NewChatView.as_view(), name='new-chat'),
    path('chat/refresh-ads/', RefreshAdsView.as_view(), name='refresh-ads'),
]