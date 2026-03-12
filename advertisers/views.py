
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.db.models.functions import Coalesce
from django.db import transaction
from decimal import Decimal
from datetime import timedelta, datetime

from .models import AdvertiserAd, UserSubscription, AdMetrics, AdEvent
from .serializers import (
    AdvertiserAdCreateSerializer,
    AdvertiserAdListSerializer,
    AdvertiserAdDetailSerializer,
    UserSubscriptionSerializer,
    DashboardDataSerializer,
    AnalyticsDataSerializer,
)
from .utils import success_response, error_response
from accounts.permissions import IsAdvertiser

from adrf.views import APIView
from asgiref.sync import sync_to_async
from django.db.models.functions import TruncDate, ExtractHour
import asyncio
from user.throttle import (
    AdEventAnonThrottle,
    AdClickAnonThrottle,
    CampaignCreateThrottle,
    SubmitPaymentThrottle,
    AnalyticsThrottle,
    DashboardThrottle
)


# ==================== PAGINATION ====================

class StandardPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


# ==================== DASHBOARD ====================

# class AdvertiserDashboardView(APIView):
#     """
#     GET: Complete dashboard with all statistics
#     Returns summary, today's highlights, performance chart, and top campaigns
#     """
#     permission_classes = [IsAuthenticated, IsAdvertiser]
    
#     def get(self, request):
#         user = request.user
#         today = timezone.now().date()
        
#         # Deactivate any expired ads before fetching data
#         self._deactivate_expired_ads(user)
        
#         # Get all campaigns
#         campaigns = AdvertiserAd.objects.filter(advertiser=user)
        
#         # Build dashboard data
#         dashboard_data = {
#             "summary": self._get_summary(campaigns),
#             "today_highlights": self._get_today_highlights(campaigns, today),
#             "performance_chart": self._get_performance_chart(campaigns, days=7),
#             "top_campaigns": self._get_top_campaigns(campaigns, limit=5)
#         }
        
#         serializer = DashboardDataSerializer(dashboard_data)
        
#         return success_response(
#             data=serializer.data,
#             message="Dashboard data retrieved successfully"
#         )
    
#     def _deactivate_expired_ads(self, user):
#         """Deactivate expired ads for this user"""
#         today = timezone.now().date()
#         AdvertiserAd.objects.filter(
#             advertiser=user,
#             is_active=True,
#             end_date__lt=today
#         ).update(is_active=False)
    
#     def _get_summary(self, campaigns):
#         """Calculate summary statistics"""
#         metrics = AdMetrics.objects.filter(ad__in=campaigns)
        
#         agg = metrics.aggregate(
#             total_clicks=Coalesce(Sum("total_clicks"), 0),
#             total_conversions=Coalesce(Sum("total_conversions"), 0),
#             total_impressions=Coalesce(Sum("total_impressions"), 0),
#             total_spent=Coalesce(Sum("total_spent"), Decimal("0.00"))
#         )
        
#         total_clicks = int(agg["total_clicks"])
#         total_conversions = int(agg["total_conversions"])
#         total_spent = Decimal(str(agg["total_spent"]))
        
#         conversion_rate = Decimal("0.00")
#         if total_clicks > 0:
#             conversion_rate = Decimal(
#                 (total_conversions / total_clicks) * 100
#             ).quantize(Decimal("0.01"))
        
#         return {
#             "active_campaigns": campaigns.filter(is_active=True, end_date__gte=timezone.now().date()).count(),
#             "total_clicks": total_clicks,
#             "conversion_rate": conversion_rate,
#             "total_spent": total_spent
#         }
    
#     def _get_today_highlights(self, campaigns, today):
#         """Get today's performance"""
#         today_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
#         today_end = timezone.make_aware(datetime.combine(today, datetime.max.time()))
        
#         today_events = AdEvent.objects.filter(
#             ad__in=campaigns,
#             timestamp__gte=today_start,
#             timestamp__lte=today_end
#         )
        
#         impressions = today_events.filter(event_type="impression").count()
#         clicks = today_events.filter(event_type="click").count()
#         spend = Decimal(str(impressions * 0.1))
        
#         avg_ctr = Decimal("0.00")
#         if impressions > 0:
#             avg_ctr = Decimal((clicks / impressions) * 100).quantize(Decimal("0.01"))
        
#         return {
#             "impressions": impressions,
#             "clicks": clicks,
#             "spend": spend,
#             "avg_ctr": avg_ctr
#         }
    
#     def _get_performance_chart(self, campaigns, days=7):
#         """Get performance data for last N days"""
#         today = timezone.now().date()
#         start_date = today - timedelta(days=days-1)
        
#         # Use datetime range for better performance
#         start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
#         end_datetime = timezone.make_aware(datetime.combine(today, datetime.max.time()))
        
#         events = AdEvent.objects.filter(
#             ad__in=campaigns,
#             timestamp__gte=start_datetime,
#             timestamp__lte=end_datetime
#         )
        
#         impressions_by_date = {}
#         clicks_by_date = {}
        
#         for event in events:
#             event_date = event.timestamp.date()
            
#             if event.event_type == "impression":
#                 impressions_by_date[event_date] = impressions_by_date.get(event_date, 0) + 1
#             elif event.event_type == "click":
#                 clicks_by_date[event_date] = clicks_by_date.get(event_date, 0) + 1
        
#         chart_data = []
#         for i in range(days):
#             date = start_date + timedelta(days=i)
#             chart_data.append({
#                 "date": date,
#                 "impressions": impressions_by_date.get(date, 0),
#                 "clicks": clicks_by_date.get(date, 0)
#             })
        
#         return chart_data
    
#     def _get_top_campaigns(self, campaigns, limit=5):
#         """Get top performing campaigns"""
#         campaigns_with_metrics = campaigns.select_related("metrics").filter(
#             metrics__total_impressions__gt=0,
#             is_active=True
#         ).order_by("-metrics__total_clicks")[:limit]
        
#         top_campaigns = []
#         for campaign in campaigns_with_metrics:
#             metrics = campaign.metrics
#             top_campaigns.append({
#                 "campaign_name": campaign.title,
#                 "impressions": metrics.total_impressions,
#                 "clicks": metrics.total_clicks,
#                 "spend": metrics.total_spent
#             })
        
#         return top_campaigns


######################## faster version for dashboard
from adrf.views import APIView
from asgiref.sync import sync_to_async
import asyncio
from django.db.models import Count

class AdvertiserDashboardView(APIView):
    """
    GET: Complete dashboard with all statistics
    Returns summary, today's highlights, performance chart, and top campaigns
    """
    permission_classes = [IsAuthenticated, IsAdvertiser]
    throttle_classes = [DashboardThrottle]

    async def get(self, request):
        user = request.user
        today = timezone.now().date()

        # Deactivate expired ads first (must complete before fetching data)
        await self._deactivate_expired_ads(user)

        # Fetch campaigns once, reuse across all methods
        campaigns = await sync_to_async(
            lambda: list(AdvertiserAd.objects.filter(advertiser=user))
        )()
        campaign_ids = [c.id for c in campaigns]

        # Run all 4 dashboard sections concurrently
        summary, today_highlights, performance_chart, top_campaigns = await asyncio.gather(
            self._get_summary(campaign_ids),
            self._get_today_highlights(campaign_ids, today),
            self._get_performance_chart(campaign_ids, days=7),
            self._get_top_campaigns(campaign_ids, limit=5)
        )

        dashboard_data = {
            "summary":           summary,
            "today_highlights":  today_highlights,
            "performance_chart": performance_chart,
            "top_campaigns":     top_campaigns
        }

        serializer = await sync_to_async(lambda: DashboardDataSerializer(dashboard_data).data)()

        return success_response(
            data=serializer,
            message="Dashboard data retrieved successfully"
        )

    async def _deactivate_expired_ads(self, user):
        today = timezone.now().date()
        await sync_to_async(
            lambda: AdvertiserAd.objects.filter(
                advertiser=user,
                is_active=True,
                end_date__lt=today
            ).update(is_active=False)
        )()

    async def _get_summary(self, campaign_ids):
        def _query():
            campaigns = AdvertiserAd.objects.filter(id__in=campaign_ids)
            metrics = AdMetrics.objects.filter(ad__in=campaigns)

            agg = metrics.aggregate(
                total_clicks=Coalesce(Sum("total_clicks"), 0),
                total_conversions=Coalesce(Sum("total_conversions"), 0),
                total_impressions=Coalesce(Sum("total_impressions"), 0),
                total_spent=Coalesce(Sum("total_spent"), Decimal("0.00"))
            )

            total_clicks      = int(agg["total_clicks"])
            total_conversions = int(agg["total_conversions"])
            total_spent       = Decimal(str(agg["total_spent"]))

            conversion_rate = Decimal("0.00")
            if total_clicks > 0:
                conversion_rate = Decimal(
                    (total_conversions / total_clicks) * 100
                ).quantize(Decimal("0.01"))

            active_count = campaigns.filter(
                is_active=True,
                end_date__gte=timezone.now().date()
            ).count()

            return {
                "active_campaigns": active_count,
                "total_clicks":     total_clicks,
                "conversion_rate":  conversion_rate,
                "total_spent":      total_spent
            }

        return await sync_to_async(_query)()

    async def _get_today_highlights(self, campaign_ids, today):
        def _query():
            today_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
            today_end   = timezone.make_aware(datetime.combine(today, datetime.max.time()))

            today_events = AdEvent.objects.filter(
                ad__in=campaign_ids,
                timestamp__gte=today_start,
                timestamp__lte=today_end
            )

            # Single DB query instead of two separate .count() calls
            counts = today_events.values("event_type").annotate(total=Count("id"))
            count_map = {row["event_type"]: row["total"] for row in counts}

            impressions = count_map.get("impression", 0)
            clicks      = count_map.get("click", 0)
            spend       = Decimal(str(impressions * 0.1))

            avg_ctr = Decimal("0.00")
            if impressions > 0:
                avg_ctr = Decimal((clicks / impressions) * 100).quantize(Decimal("0.01"))

            return {
                "impressions": impressions,
                "clicks":      clicks,
                "spend":       spend,
                "avg_ctr":     avg_ctr
            }

        return await sync_to_async(_query)()

    async def _get_performance_chart(self, campaign_ids, days=7):
        def _query():
            today      = timezone.now().date()
            start_date = today - timedelta(days=days - 1)

            start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
            end_datetime   = timezone.make_aware(datetime.combine(today, datetime.max.time()))

            # Aggregate at DB level — no more Python-side looping over raw events
            events = (
                AdEvent.objects
                .filter(
                    ad__in=campaign_ids,
                    timestamp__gte=start_datetime,
                    timestamp__lte=end_datetime
                )
                .annotate(event_date=TruncDate("timestamp"))
                .values("event_date", "event_type")
                .annotate(total=Count("id"))
            )

            impressions_by_date = {}
            clicks_by_date      = {}

            for row in events:
                d = row["event_date"]
                if row["event_type"] == "impression":
                    impressions_by_date[d] = row["total"]
                elif row["event_type"] == "click":
                    clicks_by_date[d] = row["total"]

            return [
                {
                    "date":        start_date + timedelta(days=i),
                    "impressions": impressions_by_date.get(start_date + timedelta(days=i), 0),
                    "clicks":      clicks_by_date.get(start_date + timedelta(days=i), 0)
                }
                for i in range(days)
            ]

        return await sync_to_async(_query)()

    async def _get_top_campaigns(self, campaign_ids, limit=5):
        def _query():
            campaigns = (
                AdvertiserAd.objects
                .filter(id__in=campaign_ids)
                .select_related("metrics")
                .filter(
                    metrics__total_impressions__gt=0,
                    is_active=True
                )
                .order_by("-metrics__total_clicks")[:limit]
            )

            return [
                {
                    "campaign_name": c.title,
                    "impressions":   c.metrics.total_impressions,
                    "clicks":        c.metrics.total_clicks,
                    "spend":         c.metrics.total_spent
                }
                for c in campaigns
            ]

        return await sync_to_async(_query)()


# ==================== ANALYTICS ====================

# class AnalyticsView(APIView):
#     """
#     GET: Complete analytics with filters
#     Query params:
#     - period: 7, 15, or 30 (days)
#     - campaign_id: specific campaign or "all"
#     """
#     permission_classes = [IsAuthenticated, IsAdvertiser]
    
#     def get(self, request):
#         user = request.user
        
#         # Deactivate expired ads first
#         self._deactivate_expired_ads(user)
        
#         # Get filters
#         period = int(request.query_params.get("period", 7))
#         campaign_id = request.query_params.get("campaign_id", "all")
        
#         # Validate period
#         if period not in [7, 15, 30]:
#             return error_response(
#                 message="Invalid period. Must be 7, 15, or 30 days",
#                 status_code=status.HTTP_400_BAD_REQUEST
#             )
        
#         # Get campaigns based on filter
#         if campaign_id == "all":
#             campaigns = AdvertiserAd.objects.filter(advertiser=user)
#             selected_campaign = "All Campaigns"
#         else:
#             try:
#                 campaign = AdvertiserAd.objects.get(
#                     id=campaign_id,
#                     advertiser=user
#                 )
#                 campaigns = AdvertiserAd.objects.filter(id=campaign_id)
#                 selected_campaign = campaign.title
#             except AdvertiserAd.DoesNotExist:
#                 return error_response(
#                     message="Campaign not found",
#                     status_code=status.HTTP_404_NOT_FOUND
#                 )
        
#         # Calculate date range
#         end_date = timezone.now().date()
#         start_date = end_date - timedelta(days=period-1)
        
#         # Build analytics data
#         analytics_data = {
#             "performance_overview": self._get_performance_overview(campaigns, start_date, end_date),
#             "performance_breakdown": self._get_performance_breakdown(campaigns, start_date, end_date),
#             "clicks_by_hour": self._get_clicks_by_hour(campaigns, start_date, end_date),
#             "campaign_performance": self._get_campaign_performance(campaigns, start_date, end_date),
#             "key_insights": self._generate_key_insights(campaigns, start_date, end_date),
#             "total_impressions": self._get_total_impressions(campaigns, start_date, end_date),
#             "total_clicks": self._get_total_clicks(campaigns, start_date, end_date),
#             "total_spend": self._get_total_spend(campaigns, start_date, end_date),
#             "selected_period": f"{period} days",
#             "selected_campaign": selected_campaign
#         }
        
#         serializer = AnalyticsDataSerializer(analytics_data)
        
#         return success_response(
#             data=serializer.data,
#             message="Analytics data retrieved successfully"
#         )
    
#     def _deactivate_expired_ads(self, user):
#         """Deactivate expired ads for this user"""
#         today = timezone.now().date()
#         AdvertiserAd.objects.filter(
#             advertiser=user,
#             is_active=True,
#             end_date__lt=today
#         ).update(is_active=False)
    
#     def _get_performance_overview(self, campaigns, start_date, end_date):
#         """Get daily performance data"""
#         start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
#         end_datetime = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        
#         events = AdEvent.objects.filter(
#             ad__in=campaigns,
#             timestamp__gte=start_datetime,
#             timestamp__lte=end_datetime
#         )
        
#         impressions_by_date = {}
#         clicks_by_date = {}
        
#         for event in events:
#             event_date = event.timestamp.date()
            
#             if event.event_type == "impression":
#                 impressions_by_date[event_date] = impressions_by_date.get(event_date, 0) + 1
#             elif event.event_type == "click":
#                 clicks_by_date[event_date] = clicks_by_date.get(event_date, 0) + 1
        
#         # Build daily data
#         performance_data = []
#         days = (end_date - start_date).days + 1
#         for i in range(days):
#             date = start_date + timedelta(days=i)
#             performance_data.append({
#                 "date": date,
#                 "impressions": impressions_by_date.get(date, 0),
#                 "clicks": clicks_by_date.get(date, 0)
#             })
        
#         return performance_data
    
#     def _get_performance_breakdown(self, campaigns, start_date, end_date):
#         """Get performance breakdown by category"""
#         start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
#         end_datetime = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        
#         events = AdEvent.objects.filter(
#             ad__in=campaigns,
#             timestamp__gte=start_datetime,
#             timestamp__lte=end_datetime,
#             event_type="impression"
#         )
        
#         # Group by campaign category
#         category_counts = {}
#         for event in events:
#             category = event.ad.category
#             category_counts[category] = category_counts.get(category, 0) + 1
        
#         total = sum(category_counts.values())
        
#         breakdown = []
#         for category, count in category_counts.items():
#             percentage = Decimal((count / total) * 100).quantize(Decimal("0.01")) if total > 0 else Decimal("0.00")
#             breakdown.append({
#                 "category": category.title(),
#                 "value": count,
#                 "percentage": percentage
#             })
        
#         # Sort by value descending
#         breakdown.sort(key=lambda x: x["value"], reverse=True)
        
#         return breakdown
    
#     def _get_clicks_by_hour(self, campaigns, start_date, end_date):
#         """Get clicks distribution by hour of day"""
#         start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
#         end_datetime = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        
#         events = AdEvent.objects.filter(
#             ad__in=campaigns,
#             timestamp__gte=start_datetime,
#             timestamp__lte=end_datetime,
#             event_type="click"
#         )
        
#         # Group by hour (0-23)
#         hour_counts = {i: 0 for i in range(24)}
#         for event in events:
#             hour = event.timestamp.hour
#             hour_counts[hour] += 1
        
#         clicks_by_hour = []
#         for hour in range(24):
#             clicks_by_hour.append({
#                 "hour": hour,
#                 "clicks": hour_counts[hour]
#             })
        
#         return clicks_by_hour
    
#     def _get_campaign_performance(self, campaigns, start_date, end_date):
#         """Get individual campaign performance"""
#         start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
#         end_datetime = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        
#         campaign_performance = []
        
#         for campaign in campaigns:
#             events = AdEvent.objects.filter(
#                 ad=campaign,
#                 timestamp__gte=start_datetime,
#                 timestamp__lte=end_datetime
#             )
            
#             impressions = events.filter(event_type="impression").count()
#             clicks = events.filter(event_type="click").count()
#             spend = Decimal(str(impressions * 0.1))
            
#             campaign_performance.append({
#                 "campaign_name": campaign.title,
#                 "impressions": impressions,
#                 "clicks": clicks,
#                 "spend": spend
#             })
        
#         # Sort by impressions descending
#         campaign_performance.sort(key=lambda x: x["impressions"], reverse=True)
        
#         return campaign_performance
    
#     def _generate_key_insights(self, campaigns, start_date, end_date):
#         """Generate key insights based on data"""
#         insights = []
        
#         start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
#         end_datetime = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        
#         # Get events
#         events = AdEvent.objects.filter(
#             ad__in=campaigns,
#             timestamp__gte=start_datetime,
#             timestamp__lte=end_datetime
#         )
        
#         total_impressions = events.filter(event_type="impression").count()
#         total_clicks = events.filter(event_type="click").count()
        
#         # Insight 1: Peak performance
#         if total_clicks > 0:
#             # Find best performing day
#             clicks_by_date = {}
#             for event in events.filter(event_type="click"):
#                 date = event.timestamp.date()
#                 clicks_by_date[date] = clicks_by_date.get(date, 0) + 1
            
#             if clicks_by_date:
#                 best_day = max(clicks_by_date, key=clicks_by_date.get)
#                 insights.append({
#                     "type": "success",
#                     "title": "Peak Performance",
#                     "message": f"Your best day was {best_day.strftime('%B %d')} with {clicks_by_date[best_day]} clicks"
#                 })
        
#         # Insight 2: Engagement trend
#         if total_impressions > 0:
#             avg_ctr = (total_clicks / total_impressions) * 100
#             if avg_ctr > 5:
#                 insights.append({
#                     "type": "success",
#                     "title": "Strong Engagement",
#                     "message": f"Your campaigns are performing well with {avg_ctr:.2f}% average engagement"
#                 })
#             else:
#                 insights.append({
#                     "type": "warning",
#                     "title": "Improve Engagement",
#                     "message": "Consider optimizing your ad content to increase click rates"
#                 })
        
#         # Insight 3: Budget optimization
#         total_spend = Decimal(str(total_impressions * 0.1))
#         if total_spend > 0 and total_clicks > 0:
#             cost_per_click = total_spend / total_clicks
#             insights.append({
#                 "type": "info",
#                 "title": "Cost Efficiency",
#                 "message": f"Your average cost per click is PKR {cost_per_click:.2f}"
#             })
        
#         return insights
    
#     def _get_total_impressions(self, campaigns, start_date, end_date):
#         """Get total impressions for period"""
#         start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
#         end_datetime = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        
#         return AdEvent.objects.filter(
#             ad__in=campaigns,
#             timestamp__gte=start_datetime,
#             timestamp__lte=end_datetime,
#             event_type="impression"
#         ).count()
    
#     def _get_total_clicks(self, campaigns, start_date, end_date):
#         """Get total clicks for period"""
#         start_datetime = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
#         end_datetime = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        
#         return AdEvent.objects.filter(
#             ad__in=campaigns,
#             timestamp__gte=start_datetime,
#             timestamp__lte=end_datetime,
#             event_type="click"
#         ).count()
    
#     def _get_total_spend(self, campaigns, start_date, end_date):
#         """Get total spend for period"""
#         impressions = self._get_total_impressions(campaigns, start_date, end_date)
#         return Decimal(str(impressions * 0.1))


############################# faster version for analytics

from adrf.views import APIView
from asgiref.sync import sync_to_async
from django.db.models.functions import TruncDate, ExtractHour
import asyncio
from user.throttle import (
    AdEventAnonThrottle,
    AdClickAnonThrottle,
    CampaignCreateThrottle,
    SubmitPaymentThrottle,
    AnalyticsThrottle,
    DashboardThrottle
)

class AnalyticsView(APIView):
    """
    GET: Complete analytics with filters
    Query params:
    - period: 7, 15, or 30 (days)
    - campaign_id: specific campaign or "all"
    """
    permission_classes = [IsAuthenticated, IsAdvertiser]
    throttle_classes = [AnalyticsThrottle]

    async def get(self, request):
        user = request.user

        # Deactivate expired ads first
        await self._deactivate_expired_ads(user)

        # Validate period
        period = int(request.query_params.get("period", 7))
        if period not in [7, 15, 30]:
            return error_response(
                message="Invalid period. Must be 7, 15, or 30 days",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Resolve campaign filter
        campaign_id = request.query_params.get("campaign_id", "all")
        try:
            campaign_ids, selected_campaign = await self._resolve_campaigns(user, campaign_id)
        except AdvertiserAd.DoesNotExist:
            return error_response(
                message="Campaign not found",
                status_code=status.HTTP_404_NOT_FOUND
            )

        end_date   = timezone.now().date()
        start_date = end_date - timedelta(days=period - 1)

        # Single shared event query result reused across all methods
        # Fetch ALL events once, pass down — no repeated DB hits
        raw_events = await self._fetch_all_events(campaign_ids, start_date, end_date)
        print(len(raw_events))

        # Aggregate totals once, reuse everywhere
        total_impressions = sum(1 for e in raw_events if e["event_type"] == "impression")
        total_clicks      = sum(1 for e in raw_events if e["event_type"] == "click")
        total_spend       = Decimal(str(total_impressions * 0.1))

        # Run all sections concurrently — they all work off raw_events in memory, no DB calls
        (
            performance_overview,
            performance_breakdown,
            clicks_by_hour,
            campaign_performance,
            key_insights,
        ) = await asyncio.gather(
            self._get_performance_overview(raw_events, start_date, end_date),
            self._get_performance_breakdown(raw_events),
            self._get_clicks_by_hour(raw_events),
            self._get_campaign_performance(campaign_ids, start_date, end_date),
            self._generate_key_insights(raw_events, total_impressions, total_clicks, total_spend),
        )

        analytics_data = {
            "performance_overview":    performance_overview,
            "performance_breakdown":   performance_breakdown,
            "clicks_by_hour":          clicks_by_hour,
            "campaign_performance":    campaign_performance,
            "key_insights":            key_insights,
            "total_impressions":       total_impressions,
            "total_clicks":            total_clicks,
            "total_spend":             total_spend,
            "selected_period":         f"{period} days",
            "selected_campaign":       selected_campaign
        }

        serializer_data = await sync_to_async(
            lambda: AnalyticsDataSerializer(analytics_data).data
        )()

        return success_response(
            data=serializer_data,
            message="Analytics data retrieved successfully"
        )

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    async def _deactivate_expired_ads(self, user):
        today = timezone.now().date()
        await sync_to_async(
            lambda: AdvertiserAd.objects.filter(
                advertiser=user, is_active=True, end_date__lt=today
            ).update(is_active=False)
        )()

    async def _resolve_campaigns(self, user, campaign_id):
        """Returns (list[int] of campaign ids, display name)."""
        def _query():
            if campaign_id == "all":
                ids  = list(AdvertiserAd.objects.filter(advertiser=user).values_list("id", flat=True))
                name = "All Campaigns"
            else:
                campaign = AdvertiserAd.objects.get(id=campaign_id, advertiser=user)
                ids  = [campaign.id]
                name = campaign.title
            return ids, name

        return await sync_to_async(_query)()

    async def _fetch_all_events(self, campaign_ids, start_date, end_date):
        """
        Single DB round-trip that fetches every event needed for the entire view.
        Returns a list of lightweight dicts — no model instance overhead.
        """
        def _query():
            start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
            end_dt   = timezone.make_aware(datetime.combine(end_date,   datetime.max.time()))

            return list(
                AdEvent.objects.filter(
                    ad__in=campaign_ids,
                    timestamp__gte=start_dt,
                    timestamp__lte=end_dt
                ).values("event_type", "timestamp", "ad__id", "ad__category")
            )

        return await sync_to_async(_query)()

    # ------------------------------------------------------------------ #
    #  All sections below are pure CPU work on in-memory data.            #
    #  No DB calls, no sync_to_async needed.                              #
    # ------------------------------------------------------------------ #

    async def _get_performance_overview(self, raw_events, start_date, end_date):
        impressions_by_date = {}
        clicks_by_date      = {}

        for e in raw_events:
            d = e["timestamp"].date()
            if e["event_type"] == "impression":
                impressions_by_date[d] = impressions_by_date.get(d, 0) + 1
            elif e["event_type"] == "click":
                clicks_by_date[d] = clicks_by_date.get(d, 0) + 1

        days = (end_date - start_date).days + 1
        return [
            {
                "date":        start_date + timedelta(days=i),
                "impressions": impressions_by_date.get(start_date + timedelta(days=i), 0),
                "clicks":      clicks_by_date.get(start_date + timedelta(days=i), 0),
            }
            for i in range(days)
        ]

    async def _get_performance_breakdown(self, raw_events):
        category_counts = {}
        for e in raw_events:
            if e["event_type"] == "impression":
                cat = e["ad__category"]
                category_counts[cat] = category_counts.get(cat, 0) + 1

        total = sum(category_counts.values())
        breakdown = [
            {
                "category":   cat.title(),
                "value":      count,
                "percentage": Decimal((count / total) * 100).quantize(Decimal("0.01")) if total else Decimal("0.00"),
            }
            for cat, count in category_counts.items()
        ]
        breakdown.sort(key=lambda x: x["value"], reverse=True)
        return breakdown

    async def _get_clicks_by_hour(self, raw_events):
        hour_counts = {i: 0 for i in range(24)}
        for e in raw_events:
            if e["event_type"] == "click":
                hour_counts[e["timestamp"].hour] += 1

        return [{"hour": h, "clicks": hour_counts[h]} for h in range(24)]

    async def _get_campaign_performance(self, campaign_ids, start_date, end_date):
        """
        Uses a single aggregated DB query instead of per-campaign COUNT loops.
        """
        def _query():
            start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
            end_dt   = timezone.make_aware(datetime.combine(end_date,   datetime.max.time()))

            # One query — DB groups and counts by (ad, event_type)
            rows = (
                AdEvent.objects.filter(
                    ad__in=campaign_ids,
                    timestamp__gte=start_dt,
                    timestamp__lte=end_dt
                )
                .values("ad__id", "ad__title", "event_type")
                .annotate(total=Count("id"))
            )

            # Merge into per-campaign dict
            perf = {}
            for row in rows:
                cid = row["ad__id"]
                if cid not in perf:
                    perf[cid] = {"campaign_name": row["ad__title"], "impressions": 0, "clicks": 0}
                if row["event_type"] == "impression":
                    perf[cid]["impressions"] = row["total"]
                elif row["event_type"] == "click":
                    perf[cid]["clicks"] = row["total"]

            result = [
                {
                    **v,
                    "spend": Decimal(str(v["impressions"] * 0.1))
                }
                for v in perf.values()
            ]
            result.sort(key=lambda x: x["impressions"], reverse=True)
            return result

        return await sync_to_async(_query)()

    async def _generate_key_insights(self, raw_events, total_impressions, total_clicks, total_spend):
        """Works entirely off pre-computed in-memory data — zero DB calls."""
        insights = []

        # Insight 1: Peak performance day
        if total_clicks > 0:
            clicks_by_date = {}
            for e in raw_events:
                if e["event_type"] == "click":
                    d = e["timestamp"].date()
                    clicks_by_date[d] = clicks_by_date.get(d, 0) + 1

            if clicks_by_date:
                best_day = max(clicks_by_date, key=clicks_by_date.get)
                insights.append({
                    "type":    "success",
                    "title":   "Peak Performance",
                    "message": f"Your best day was {best_day.strftime('%B %d')} with {clicks_by_date[best_day]} clicks"
                })

        # Insight 2: Engagement trend
        if total_impressions > 0:
            avg_ctr = (total_clicks / total_impressions) * 100
            if avg_ctr > 5:
                insights.append({
                    "type":    "success",
                    "title":   "Strong Engagement",
                    "message": f"Your campaigns are performing well with {avg_ctr:.2f}% average engagement"
                })
            else:
                insights.append({
                    "type":    "warning",
                    "title":   "Improve Engagement",
                    "message": "Consider optimizing your ad content to increase click rates"
                })

        # Insight 3: Cost efficiency
        if total_spend > 0 and total_clicks > 0:
            cost_per_click = total_spend / total_clicks
            insights.append({
                "type":    "info",
                "title":   "Cost Efficiency",
                "message": f"Your average cost per click is PKR {cost_per_click:.2f}"
            })

        return insights


# ==================== CAMPAIGN CREATION ====================

class CampaignCreateView(APIView):
    """
    POST: Create a new campaign
    Note: Campaign is created as inactive until payment is completed
    """
    permission_classes = [IsAuthenticated, IsAdvertiser]
    throttle_classes = [CampaignCreateThrottle]
    
    @transaction.atomic
    def post(self, request):
        serializer = AdvertiserAdCreateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="Validation failed",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        # Check active subscription
        try:
            user_subscription = UserSubscription.objects.select_for_update().select_related('plan').get(
                user=request.user,
                is_active=True
            )
        except UserSubscription.DoesNotExist:
            return error_response(
                message="No active subscription found",
                status_code=status.HTTP_403_FORBIDDEN
            )
        
        start_date = serializer.validated_data.get("start_date")
        end_date = serializer.validated_data.get("end_date")
        daily_budget = serializer.validated_data.get("daily_budget")
        
        # Validate dates
        today = timezone.now().date()
        if start_date < today:
            return error_response(
                message="Start date cannot be in the past",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        if end_date < start_date:
            return error_response(
                message="End date must be after start date",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate budget and impressions
        duration_days = (end_date - start_date).days + 1  # +1 to include both start and end date
        total_budget = daily_budget * duration_days
        required_impressions = int(total_budget * 10)
        
        # Check impression availability
        if user_subscription.remaining_impressions < required_impressions:
            return error_response(
                message="Insufficient impressions in your plan",
                errors={
                    "required_impressions": required_impressions,
                    "available_impressions": user_subscription.remaining_impressions
                },
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        # Deduct impressions from subscription
        user_subscription.remaining_impressions -= required_impressions
        user_subscription.used_impressions += required_impressions
        user_subscription.save()
        
        # Create campaign (inactive until payment)
        campaign = AdvertiserAd.objects.create(
            advertiser=request.user,
            title=serializer.validated_data.get("title"),
            description=serializer.validated_data.get("description"),
            ad_type=serializer.validated_data.get("ad_type"),
            category=serializer.validated_data.get("category"),
            url=serializer.validated_data.get("url"),
            media_file=serializer.validated_data.get("media_file"),
            target_keywords=serializer.validated_data.get("target_keywords", []),
            daily_budget=daily_budget,
            total_budget=total_budget,
            total_impressions=required_impressions,
            remaining_impressions=required_impressions,
            start_date=start_date,
            end_date=end_date,
            payment_status="paid",
            is_active=True  
        )
        
        # Create metrics record
        AdMetrics.objects.create(ad=campaign)
        
        response_data = AdvertiserAdDetailSerializer(campaign).data
        
        return success_response(
            data=response_data,
            message="Campaign created successfully.",
            status_code=status.HTTP_201_CREATED
        )


class CampaignPreviewView(APIView):
    """POST: Preview campaign budget and requirements"""
    permission_classes = [IsAuthenticated, IsAdvertiser]
    
    def post(self, request):
        daily_budget = request.data.get("daily_budget")
        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")
        
        if not all([daily_budget, start_date, end_date]):
            return error_response(
                message="Missing required fields: daily_budget, start_date, end_date",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate budget
        try:
            daily_budget = Decimal(str(daily_budget))
            if daily_budget <= 0:
                raise ValueError("Budget must be positive")
        except (ValueError, Exception):
            return error_response(
                message="Invalid daily budget. Must be a positive number.",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate dates
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            return error_response(
                message="Invalid date format. Use YYYY-MM-DD.",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        today = timezone.now().date()
        if start < today:
            return error_response(
                message="Start date cannot be in the past.",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        if end < start:
            return error_response(
                message="End date must be after start date.",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate campaign details
        duration_days = (end - start).days + 1  # +1 to include both dates
        total_budget = daily_budget * duration_days
        total_impressions = int(total_budget * 10)
        
        # Check subscription
        try:
            user_subscription = UserSubscription.objects.select_related('plan').get(
                user=request.user,
                is_active=True
            )
            remaining_after = user_subscription.remaining_impressions - total_impressions
            has_enough = remaining_after >= 0
        except UserSubscription.DoesNotExist:
            user_subscription = None
            remaining_after = 0
            has_enough = False
        
        preview_data = {
            "daily_budget": str(daily_budget),
            "duration_days": duration_days,
            "total_budget": str(total_budget),
            "total_impressions": total_impressions,
            "subscription": {
                "plan_name": user_subscription.plan.display_name if user_subscription else "No Plan",
                "current_remaining": user_subscription.remaining_impressions if user_subscription else 0,
                "after_campaign": remaining_after if remaining_after >= 0 else 0,
                "has_enough_impressions": has_enough
            }
        }
        
        return success_response(
            data=preview_data,
            message="Campaign preview generated successfully"
        )


class CampaignListView(generics.ListAPIView):
    """GET: List all campaigns for authenticated advertiser"""
    serializer_class = AdvertiserAdListSerializer
    permission_classes = [IsAuthenticated, IsAdvertiser]
    pagination_class = StandardPagination
    
    def get_queryset(self):
        # Deactivate expired ads first
        today = timezone.now().date()
        AdvertiserAd.objects.filter(
            advertiser=self.request.user,
            is_active=True,
            end_date__lt=today
        ).update(is_active=False)
        
        return AdvertiserAd.objects.filter(
            advertiser=self.request.user
        ).select_related('metrics').order_by("-created_at")
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={'request': request})
            paginated_response = self.get_paginated_response(serializer.data)
            
            return success_response(
                data={
                    "campaigns": paginated_response.data.get("results"),
                    "pagination": {
                        "count": paginated_response.data.get("count"),
                        "next": paginated_response.data.get("next"),
                        "previous": paginated_response.data.get("previous"),
                    }
                },
                message="Campaigns retrieved successfully"
            )
        
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return success_response(
            data={"campaigns": serializer.data},
            message="Campaigns retrieved successfully"
        )


class CampaignDetailView(APIView):
    """GET: Get detailed information about a specific campaign"""
    permission_classes = [IsAuthenticated, IsAdvertiser]
    
    def get(self, request, campaign_id):
        campaign = get_object_or_404(
            AdvertiserAd,
            id=campaign_id,
            advertiser=request.user
        )
        
        # Check and update if expired
        if campaign.is_expired and campaign.is_active:
            campaign.is_active = False
            campaign.save(update_fields=['is_active', 'updated_at'])
        
        serializer = AdvertiserAdDetailSerializer(campaign)
        return success_response(
            data=serializer.data,
            message="Campaign details retrieved successfully"
        )


class CampaignUpdateView(APIView):
    """PATCH: Update campaign details (limited fields only)"""
    permission_classes = [IsAuthenticated, IsAdvertiser]
    
    def patch(self, request, campaign_id):
        campaign = get_object_or_404(
            AdvertiserAd,
            id=campaign_id,
            advertiser=request.user
        )
        
        # Only allow updating these fields
        allowed_fields = ["title", "description", "category", "is_active"]
        update_data = {k: v for k, v in request.data.items() if k in allowed_fields}
        
        if not update_data:
            return error_response(
                message="No valid fields to update",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate is_active updates
        if "is_active" in update_data:
            # Cannot activate expired campaigns
            if update_data["is_active"] and campaign.is_expired:
                return error_response(
                    message="Cannot activate an expired campaign",
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # Cannot activate unpaid campaigns
            if update_data["is_active"] and campaign.payment_status != "paid":
                return error_response(
                    message="Cannot activate campaign with pending payment",
                    status_code=status.HTTP_400_BAD_REQUEST
                )
        
        # Apply updates
        for field, value in update_data.items():
            setattr(campaign, field, value)
        
        campaign.save()
        
        serializer = AdvertiserAdDetailSerializer(campaign)
        return success_response(
            data=serializer.data,
            message="Campaign updated successfully"
        )


class CampaignDeleteView(APIView):
    """DELETE: Soft delete campaign by deactivating it"""
    permission_classes = [IsAuthenticated, IsAdvertiser]
    
    def delete(self, request, campaign_id):
        campaign = get_object_or_404(
            AdvertiserAd,
            id=campaign_id,
            advertiser=request.user
        )
        
        # Soft delete by deactivating
        campaign.is_active = False
        campaign.save(update_fields=['is_active', 'updated_at'])
        
        return success_response(
            message="Campaign deactivated successfully",
            status_code=status.HTTP_200_OK
        )


class UserSubscriptionView(APIView):
    """GET: Get current user's subscription details"""
    permission_classes = [IsAuthenticated, IsAdvertiser]
    
    def get(self, request):
        try:
            subscription = UserSubscription.objects.select_related('plan').get(
                user=request.user,
                is_active=True
            )
            serializer = UserSubscriptionSerializer(subscription)
            return success_response(
                data=serializer.data,
                message="Subscription details retrieved successfully"
            )
        except UserSubscription.DoesNotExist:
            return error_response(
                message="No active subscription found",
                status_code=status.HTTP_404_NOT_FOUND
            )


# ==================== AD TRACKING ====================

class AdClickRedirectView(APIView):
    """
    GET: Handle ad click and redirect to destination
    This is a public endpoint called when users click on ads
    """
    permission_classes = []

    def get(self, request, ad_id):
        ad = get_object_or_404(AdvertiserAd, id=ad_id, is_active=True)
        
        # Verify ad is live
        if not ad.is_live:
            return error_response(
                message="Ad is not currently active",
                status_code=status.HTTP_404_NOT_FOUND
            )
        
        # Record the click event
        AdEvent.objects.create(ad=ad, event_type="click")
        
        # Update metrics
        metrics, _ = AdMetrics.objects.get_or_create(ad=ad)
        metrics.total_clicks += 1
        metrics.save(update_fields=['total_clicks', 'updated_at'])

        # Redirect to the actual destination
        return redirect(ad.url)


class AdEventTrackingView(APIView):
    """
    POST: Track ad events (impression, click, conversion)
    This endpoint is public so it can be called by any visitor seeing the ad
    """
    permission_classes = []
    throttle_classes = [AdEventAnonThrottle]

    def post(self, request, ad_id):
        event_type = request.data.get("event_type")
        
        # Validate event type
        valid_events = ["impression", "click", "conversion"]
        if event_type not in valid_events:
            return error_response(
                message="Invalid event type. Must be one of: impression, click, conversion",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        # Get ad
        ad = get_object_or_404(AdvertiserAd, id=ad_id)
        
        # Check if ad is live (only for impressions and clicks)
        if event_type in ["impression", "click"] and not ad.is_live:
            return error_response(
                message=f"Ad is not currently active ,{ad.is_live}",
                status_code=status.HTTP_404_NOT_FOUND
            )

        # Record the event
        AdEvent.objects.create(
            ad=ad,
            event_type=event_type,
        )

        # Update aggregated metrics
        metrics, _ = AdMetrics.objects.get_or_create(ad=ad)
        
        if event_type == "impression":
            metrics.total_impressions += 1
            
            # Deduct from ad's remaining impressions
            if ad.remaining_impressions > 0:
                ad.remaining_impressions -= 1
                
                # Auto-deactivate if budget runs out
                if ad.remaining_impressions <= 0:
                    ad.is_active = False
                
                ad.save(update_fields=['remaining_impressions', 'is_active', 'updated_at'])
            
            # Update spend (0.1 PKR per impression)
            metrics.total_spent += Decimal("0.1")

        elif event_type == "click":
            metrics.total_clicks += 1

        elif event_type == "conversion":
            metrics.total_conversions += 1

        metrics.save(update_fields=['total_impressions', 'total_clicks', 'total_conversions', 'total_spent', 'updated_at'])

        return success_response(
            message=f"Event '{event_type}' recorded successfully",
            data={"event_type": event_type, "ad_id": ad_id}
        )
    



# Add these imports at the top
from .models import SubscriptionPlan, SubscriptionPayment, PaymentMethod
from .serializers import SubscriptionPaymentCreateSerializer

# ... [Keep all your existing views] ...

# ==================== PAYMENT VIEWS ====================

class PaymentInstructionView(APIView):
    """GET: Get payment instructions for a specific plan"""
    permission_classes = [IsAuthenticated, IsAdvertiser]

    def get(self, request, plan_id):
        plan = get_object_or_404(SubscriptionPlan, id=plan_id, is_active=True)

        payment_methods = {
            "EASYPAISA": {
                "number": "03XX-XXXXXXX",
                "name": "Easypaisa",
                "instructions": "Transfer exact amount to 03XX-XXXXXXX via Easypaisa. Save the transaction ID."
            },
            "JAZZCASH": {
                "number": "03YY-YYYYYYY",
                "name": "JazzCash",
                "instructions": "Transfer exact amount to 03YY-YYYYYYY via JazzCash. Save the transaction ID."
            },
            "CARD": {
                "number": "**** **** **** 1234",
                "name": "Credit/Debit Card",
                "instructions": "Pay via card and provide the reference number."
            }
        }

        return success_response(
            data={
                "plan_name": plan.display_name,
                "plan_price": str(plan.price),
                "impression_limit": plan.impression_limit,
                "payment_methods": payment_methods
            },
            message="Payment instructions retrieved successfully"
        )


class SubmitPaymentView(APIView):
    """POST: Submit payment proof for admin approval"""
    permission_classes = [IsAuthenticated, IsAdvertiser]
    throttle_classes = [SubmitPaymentThrottle]

    @transaction.atomic
    def post(self, request):
        # 1. Validate input
        serializer = SubscriptionPaymentCreateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="Validation failed",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # 2. Check if user already has a pending payment
        existing_pending = SubscriptionPayment.objects.filter(
            user=request.user,
            status=SubscriptionPayment.STATUS_PENDING
        ).exists()
        
        if existing_pending:
            return error_response(
                message="You already have a pending payment awaiting approval",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # 3. Create payment record
        payment = serializer.save(user=request.user)

        return success_response(
            data={
                "payment_id": str(payment.id),
                "status": payment.status,
                "plan": payment.plan.display_name,
                "amount": str(payment.plan.price),
                "transaction_id": payment.transaction_id
            },
            message="Payment submitted successfully. Awaiting admin approval.",
            status_code=status.HTTP_201_CREATED
        )


class UserPaymentHistoryView(APIView):
    """GET: View user's payment history"""
    permission_classes = [IsAuthenticated, IsAdvertiser]

    def get(self, request):
        payments = SubscriptionPayment.objects.filter(
            user=request.user
        ).select_related('plan').order_by('-created_at')

        payment_data = []
        for payment in payments:
            payment_data.append({
                "id": str(payment.id),
                "plan": payment.plan.display_name,
                "amount": str(payment.plan.price),
                "payment_method": payment.payment_method,
                "transaction_id": payment.transaction_id,
                "status": payment.status,
                "paid_at": payment.paid_at,
                "created_at": payment.created_at
            })

        return success_response(
            data={"payments": payment_data},
            message="Payment history retrieved successfully"
        )