from django.urls import path
from .views import (
    AdvertiserDashboardView,
    AnalyticsView,
    CampaignCreateView,
    CampaignPreviewView,
    CampaignListView,
    CampaignDetailView,
    CampaignUpdateView,
    CampaignDeleteView,
    UserSubscriptionView,
    AdClickRedirectView,
    AdEventTrackingView,
    PaymentInstructionView,      # ← FIXED NAME
    SubmitPaymentView,            # ← FIXED NAME
    UserPaymentHistoryView,       # ← NEW
)

app_name = "advertiser"

urlpatterns = [
    # ==================== DASHBOARD ====================
    path(
        "dashboard/",
        AdvertiserDashboardView.as_view(),
        name="dashboard"
    ),
    
    # ==================== ANALYTICS ====================
    path(
        "analytics/",
        AnalyticsView.as_view(),
        name="analytics"
    ),
    
    # ==================== SUBSCRIPTION ====================
    path(
        "subscription/",
        UserSubscriptionView.as_view(),
        name="user-subscription"
    ),
    
    # ==================== PAYMENT ====================
    path(
        "subscriptions/<int:plan_id>/payment-instructions/",
        PaymentInstructionView.as_view(),
        name="payment-instructions"
    ),
    path(
        "subscriptions/payment/submit/",
        SubmitPaymentView.as_view(),
        name="payment-submit"
    ),
    path(
        "payments/history/",
        UserPaymentHistoryView.as_view(),
        name="payment-history"
    ),
    
    # ==================== CAMPAIGNS ====================
    path(
        "campaigns/preview/",
        CampaignPreviewView.as_view(),
        name="campaign-preview"
    ),
    path(
        "campaigns/",
        CampaignListView.as_view(),
        name="campaign-list"
    ),
    path(
        "campaigns/create/",
        CampaignCreateView.as_view(),
        name="campaign-create"
    ),
    path(
        "campaigns/<int:campaign_id>/",
        CampaignDetailView.as_view(),
        name="campaign-detail"
    ),
    path(
        "campaigns/<int:campaign_id>/update/",
        CampaignUpdateView.as_view(),
        name="campaign-update"
    ),
    path(
        "campaigns/<int:campaign_id>/delete/",
        CampaignDeleteView.as_view(),
        name="campaign-delete"
    ),
    
    # ==================== AD TRACKING (PUBLIC) ====================
    path(
        "ads/<int:ad_id>/click/", 
        AdClickRedirectView.as_view(), 
        name="ad-click-redirect"
    ),
    path(
        "ads/<int:ad_id>/track/", 
        AdEventTrackingView.as_view(), 
        name="ad-event-track"
    ),
]