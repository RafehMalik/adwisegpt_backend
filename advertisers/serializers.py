
from rest_framework import serializers
from .models import AdvertiserAd, SubscriptionPlan, UserSubscription, AdMetrics
from django.urls import reverse


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """Simple subscription plan serializer"""
    class Meta:
        model = SubscriptionPlan
        fields = ["id", "name", "display_name", "impression_limit", "price"]


class UserSubscriptionSerializer(serializers.ModelSerializer):
    """User subscription with remaining impressions"""
    plan = SubscriptionPlanSerializer(read_only=True)
    
    class Meta:
        model = UserSubscription
        fields = [
            "id",
            "plan",
            "remaining_impressions",
            "used_impressions",
            "is_active",
            "expires_at",
            "created_at"
        ]


class AdvertiserAdCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating campaigns"""
    class Meta:
        model = AdvertiserAd
        fields = [
            "title",
            "description",
            "ad_type",
            "category",
            "url",
            "media_file",
            "target_keywords",
            "daily_budget",
            "start_date",
            "end_date",
        ]
    
    def validate_daily_budget(self, value):
        """Validate daily budget is positive"""
        if value <= 0:
            raise serializers.ValidationError("Daily budget must be greater than 0")
        return value
    
    def validate(self, attrs):
        """Validate start and end dates"""
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")
        
        if start_date and end_date:
            if start_date > end_date:
                raise serializers.ValidationError({
                    "end_date": "End date must be after start date"
                })
        
        return attrs


class AdvertiserAdListSerializer(serializers.ModelSerializer):
    """Serializer for listing campaigns"""
    duration_days = serializers.SerializerMethodField()
    click_url = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    
    class Meta:
        model = AdvertiserAd
        fields = [
            "id",
            "title",
            "ad_type",
            "category",
            "total_budget",
            "total_impressions",
            "remaining_impressions",
            "is_active",
            "payment_status",
            "start_date",
            "end_date",
            "duration_days",
            "status",
            "click_url",
            "created_at",
        ]
    
    def get_duration_days(self, obj):
        """Calculate campaign duration"""
        return obj.duration_days
    
    def get_click_url(self, obj):
        """Generate the backend tracking URL"""
        request = self.context.get('request')
        path = reverse('advertiser:ad-click-redirect', kwargs={'ad_id': obj.id})
        
        if request:
            return request.build_absolute_uri(path)
        return path
    
    def get_status(self, obj):
        """Get human-readable campaign status"""
        if obj.is_expired:
            return "expired"
        elif not obj.is_active:
            return "inactive"
        elif obj.payment_status != "paid":
            return "pending_payment"
        elif obj.remaining_impressions <= 0:
            return "budget_exhausted"
        elif obj.is_live:
            return "active"
        else:
            return "scheduled"


class AdvertiserAdDetailSerializer(serializers.ModelSerializer):
    """Serializer for campaign details"""
    duration_days = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    metrics = serializers.SerializerMethodField()
    
    class Meta:
        model = AdvertiserAd
        fields = [
            "id",
            "title",
            "description",
            "ad_type",
            "category",
            "url",
            "media_file",
            "target_keywords",
            "daily_budget",
            "total_budget",
            "total_impressions",
            "remaining_impressions",
            "is_active",
            "payment_status",
            "start_date",
            "end_date",
            "duration_days",
            "status",
            "metrics",
            "created_at",
            "updated_at",
        ]
    
    def get_duration_days(self, obj):
        """Calculate campaign duration"""
        return obj.duration_days
    
    def get_status(self, obj):
        """Get human-readable campaign status"""
        if obj.is_expired:
            return "expired"
        elif not obj.is_active:
            return "inactive"
        elif obj.payment_status != "paid":
            return "pending_payment"
        elif obj.remaining_impressions <= 0:
            return "budget_exhausted"
        elif obj.is_live:
            return "active"
        else:
            return "scheduled"
    
    def get_metrics(self, obj):
        """Get campaign metrics if available"""
        try:
            metrics = obj.metrics
            return {
                "total_impressions": metrics.total_impressions,
                "total_clicks": metrics.total_clicks,
                "total_conversions": metrics.total_conversions,
                "total_spent": str(metrics.total_spent),
                "ctr": self._calculate_ctr(metrics),
                "conversion_rate": self._calculate_conversion_rate(metrics)
            }
        except AdMetrics.DoesNotExist:
            return None
    
    def _calculate_ctr(self, metrics):
        """Calculate Click-Through Rate"""
        if metrics.total_impressions > 0:
            return round((metrics.total_clicks / metrics.total_impressions) * 100, 2)
        return 0.0
    
    def _calculate_conversion_rate(self, metrics):
        """Calculate Conversion Rate"""
        if metrics.total_clicks > 0:
            return round((metrics.total_conversions / metrics.total_clicks) * 100, 2)
        return 0.0


# ==================== DASHBOARD SERIALIZERS ====================

class DashboardSummarySerializer(serializers.Serializer):
    """Dashboard summary statistics"""
    active_campaigns = serializers.IntegerField()
    total_clicks = serializers.IntegerField()
    conversion_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    total_spent = serializers.DecimalField(max_digits=12, decimal_places=2)


class TodayHighlightsSerializer(serializers.Serializer):
    """Today's performance highlights"""
    impressions = serializers.IntegerField()
    clicks = serializers.IntegerField()
    spend = serializers.DecimalField(max_digits=10, decimal_places=2)
    avg_ctr = serializers.DecimalField(max_digits=5, decimal_places=2)


class PerformanceChartSerializer(serializers.Serializer):
    """Performance chart data point"""
    date = serializers.DateField()
    impressions = serializers.IntegerField()
    clicks = serializers.IntegerField()


class TopCampaignSerializer(serializers.Serializer):
    """Top performing campaign row"""
    campaign_name = serializers.CharField()
    impressions = serializers.IntegerField()
    clicks = serializers.IntegerField()
    spend = serializers.DecimalField(max_digits=10, decimal_places=2)


class DashboardDataSerializer(serializers.Serializer):
    """Complete dashboard data"""
    summary = DashboardSummarySerializer()
    today_highlights = TodayHighlightsSerializer()
    performance_chart = PerformanceChartSerializer(many=True)
    top_campaigns = TopCampaignSerializer(many=True)


# ==================== ANALYTICS SERIALIZERS ====================

class PerformanceOverviewSerializer(serializers.Serializer):
    """Performance overview chart data"""
    date = serializers.DateField()
    impressions = serializers.IntegerField()
    clicks = serializers.IntegerField()


class PerformanceBreakdownSerializer(serializers.Serializer):
    """Performance breakdown by category"""
    category = serializers.CharField()
    value = serializers.IntegerField()
    percentage = serializers.DecimalField(max_digits=5, decimal_places=2)


class ClicksByHourSerializer(serializers.Serializer):
    """Clicks distribution by hour"""
    hour = serializers.IntegerField()
    clicks = serializers.IntegerField()


class CampaignPerformanceSerializer(serializers.Serializer):
    """Individual campaign performance details"""
    campaign_name = serializers.CharField()
    impressions = serializers.IntegerField()
    clicks = serializers.IntegerField()
    spend = serializers.DecimalField(max_digits=10, decimal_places=2)


class KeyInsightSerializer(serializers.Serializer):
    """Key insights for campaigns"""
    type = serializers.CharField()
    title = serializers.CharField()
    message = serializers.CharField()


class AnalyticsDataSerializer(serializers.Serializer):
    """Complete analytics data"""
    performance_overview = PerformanceOverviewSerializer(many=True)
    performance_breakdown = PerformanceBreakdownSerializer(many=True)
    clicks_by_hour = ClicksByHourSerializer(many=True)
    campaign_performance = CampaignPerformanceSerializer(many=True)
    key_insights = KeyInsightSerializer(many=True)
    
    # Summary metrics
    total_impressions = serializers.IntegerField()
    total_clicks = serializers.IntegerField()
    total_spend = serializers.DecimalField(max_digits=12, decimal_places=2)
    
    # Filters info
    selected_period = serializers.CharField()
    selected_campaign = serializers.CharField()


from rest_framework import serializers
from .models import SubscriptionPayment, PaymentMethod

class SubscriptionPaymentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating payment submissions"""
    
    class Meta:
        model = SubscriptionPayment
        fields = [
            "plan",
            "payment_method",  # ← ADDED THIS
            "transaction_id",
            "paid_at",
        ]

    def validate_transaction_id(self, value):
        """Ensure transaction ID is unique"""
        if SubscriptionPayment.objects.filter(transaction_id=value).exists():
            raise serializers.ValidationError(
                "This transaction ID has already been used. Please verify your transaction ID."
            )
        return value

    def validate_payment_method(self, value):
        """Validate payment method is one of the allowed choices"""
        if value not in dict(PaymentMethod.choices):
            raise serializers.ValidationError(
                f"Invalid payment method. Must be one of: {', '.join(dict(PaymentMethod.choices).keys())}"
            )
        return value

    def validate(self, attrs):
        """Additional validation"""
        # Ensure plan is active
        plan = attrs.get('plan')
        if not plan.is_active:
            raise serializers.ValidationError({
                "plan": "This subscription plan is no longer available."
            })
        
        return attrs


class SubscriptionPaymentListSerializer(serializers.ModelSerializer):
    """Serializer for listing payment records"""
    plan_name = serializers.CharField(source='plan.display_name', read_only=True)
    plan_price = serializers.DecimalField(
        source='plan.price',
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    
    class Meta:
        model = SubscriptionPayment
        fields = [
            "id",
            "plan_name",
            "plan_price",
            "payment_method",
            "transaction_id",
            "status",
            "paid_at",
            "created_at"
        ]
