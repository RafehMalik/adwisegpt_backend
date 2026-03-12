import random
import re
import logging
import numpy as np

from decimal import Decimal
from sklearn.metrics.pairwise import cosine_similarity

from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.db import transaction
from django.db.models import F, DecimalField, Count
from django.db.models.functions import Cast

from rest_framework.response import Response
from rest_framework import status

from user.ad_retrieval import retrieve_ads_for_user
from advertisers.models import AdvertiserAd, AdEvent, AdMetrics
from user.models import UserPreference

logger = logging.getLogger(__name__)


# ============================================================
# EMAIL
# ============================================================

def send_contact_email(user_name: str, user_email: str, subject: str, message: str):
    admin_emails = []
    admins = getattr(settings, "ADMINS", None)
    if admins:
        admin_emails = [a[1] for a in admins if len(a) >= 2 and a[1]]

    if not admin_emails:
        email_host_user = getattr(settings, "EMAIL_HOST_USER", None)
        if email_host_user:
            admin_emails = [email_host_user]

    if not admin_emails:
        return False

    full_subject = f"Contact Form: {subject} - AdWiseGPT"
    full_message = (
        f"You have received a new message from the AdWiseGPT contact form:\n\n"
        f"Name: {user_name}\n"
        f"Email: {user_email}\n\n"
        f"Message:\n{message}\n"
    )
    from_email = (
        getattr(settings, "DEFAULT_FROM_EMAIL", None)
        or getattr(settings, "EMAIL_HOST_USER", None)
        or "noreply@adwisegpt.local"
    )

    try:
        send_mail(full_subject, full_message, from_email, admin_emails, fail_silently=False)
        return True
    except Exception:
        return False


# ============================================================
# RESPONSE HELPERS
# ============================================================

def success_response(data=None, message="Success", status_code=status.HTTP_200_OK):
    return Response({"success": True, "message": message, "data": data}, status=status_code)


def error_response(message="Something went wrong", errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({"success": False, "message": message, "errors": errors}, status=status_code)


# ============================================================
# INTENT DETECTION
# ============================================================

def is_filler_message(message):
    if len(message.strip()) < 10:
        return True

    fillers = {
        'ok', 'okay', 'thanks', 'thank you', 'cool', 'nice', 'wow',
        'hello', 'hi', 'hey', 'yes', 'no', 'sure', 'fine', 'perfect',
        'great', 'understood', 'i see', 'got it', 'tell me more'
    }
    clean_msg = re.sub(r'[^\w\s]', '', message.lower()).strip()
    return clean_msg in fillers


def detect_intent_shift(current_message, previous_messages, threshold=0.5):
    if not previous_messages:
        return False

    if is_filler_message(current_message):
        logger.info(f"Intent shift bypassed: Filler detected ('{current_message}')")
        return False

    try:
        from user.ad_retrieval import get_retrieval_system
        system = get_retrieval_system()

        all_texts = [current_message] + previous_messages
        all_vecs = system.embeddings.embed_documents(all_texts)

        current_vec = all_vecs[0]
        prev_vecs = all_vecs[1:]

        similarities = [
            cosine_similarity([current_vec], [pv])[0][0]
            for pv in prev_vecs
        ]

        max_similarity = max(similarities) if similarities else 1.0
        is_shifted = max_similarity < threshold

        logger.info(
            f"Intent shift | current: '{current_message}' | "
            f"prev: {previous_messages} | "
            f"max_sim: {max_similarity:.3f} | threshold: {threshold} | "
            f"shifted: {is_shifted}"
        )
        return is_shifted

    except Exception as e:
        logger.error(f"Intent detection error: {e}")
        return False


# ============================================================
# SHARED HELPERS
# ============================================================

def _record_impressions(ads, session, request):
    """
    Shared bulk impression tracking used by both
    get_ads_with_tracking and _get_fallback_ads_for_new_session.
    Wrapped in transaction.atomic() — all writes succeed or none do.
    """
    ad_ids = [ad.id for ad in ads]

    with transaction.atomic():
        # 1 query: bulk create impression events
        AdEvent.objects.bulk_create([
            AdEvent(ad=ad, event_type="impression") for ad in ads
        ])

        # 1 query: decrement remaining impressions atomically
        AdvertiserAd.objects.filter(id__in=ad_ids).update(
            remaining_impressions=F('remaining_impressions') - 1
        )

        # 1 query: deactivate exhausted ads
        AdvertiserAd.objects.filter(
            id__in=ad_ids,
            remaining_impressions__lte=0
        ).update(is_active=False)

        # 1 query: ensure metrics rows exist for all ads
        existing_metric_ids = set(
            AdMetrics.objects.filter(ad_id__in=ad_ids).values_list('ad_id', flat=True)
        )
        missing = [aid for aid in ad_ids if aid not in existing_metric_ids]
        if missing:
            AdMetrics.objects.bulk_create([AdMetrics(ad_id=aid) for aid in missing])

        # 1 query: bulk update metrics
        AdMetrics.objects.filter(ad_id__in=ad_ids).update(
            total_impressions=F('total_impressions') + 1,
            total_spent=F('total_spent') + Cast(
                Decimal("0.10"),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )


def _build_ad_result(ads, request):
    """Shared result serialization used by both tracking functions."""
    result = []
    for ad in ads:
        click_path = reverse('advertiser:ad-click-redirect', kwargs={'ad_id': ad.id})
        click_url = request.build_absolute_uri(click_path) if request else click_path

        media_url = None
        if ad.media_file:
            try:
                media_url = request.build_absolute_uri(ad.media_file.url) if request else ad.media_file.url
            except Exception:
                pass

        result.append({
            'id':          ad.id,
            'title':       ad.title,
            'description': ad.description,
            'url':         ad.url,
            'click_url':   click_url,
            'media_url':   media_url,
            'category':    ad.get_category_display(),
        })
    return result


def _get_fallback_ads(user, limit):
    """Get random ads when no query context exists."""
    today = timezone.now().date()

    try:
        prefs = UserPreference.objects.get(user=user)
        categories = prefs.interest_categories or []
    except UserPreference.DoesNotExist:
        categories = []

    base_qs = AdvertiserAd.objects.filter(
        is_active=True,
        remaining_impressions__gt=0,
        start_date__lte=today,
        end_date__gte=today
    )

    if categories:
        base_qs = base_qs.filter(category__in=categories)

    # Avoid order_by('?') full table scan — random offset instead
    count = base_qs.count()
    if not count:
        return []

    offset = random.randint(0, max(0, count - limit))
    return list(base_qs.values_list('id', flat=True)[offset:offset + limit])


def _apply_frequency_cap(session, ad_ids, max_impressions=10):
    impression_counts = (
        AdEvent.objects
        .filter(
            ad_id__in=ad_ids,
            event_type='impression',
            timestamp__gte=session.started_at
        )
        .values('ad_id')
        .annotate(count=Count('id'))
    )

    counts_by_ad = {row['ad_id']: row['count'] for row in impression_counts}
    logger.info(f"Frequency cap counts for session {session.session_id}: {counts_by_ad}")

    return [
        ad_id for ad_id in ad_ids
        if counts_by_ad.get(ad_id, 0) < max_impressions
    ]


# ============================================================
# MAIN AD FUNCTIONS
# ============================================================

def get_ads_with_tracking(user, session, current_message, chat_history, request, limit=3):
    today = timezone.now().date()

    try:
        prefs = UserPreference.objects.get(user=user)
        if prefs.complete_opt_out:
            return []
    except UserPreference.DoesNotExist:
        pass

    if session.message_count <= 1:
        logger.info(f"First message in session {session.session_id} - using fallback ads")
        candidate_ids = _get_fallback_ads(user, limit * 2)
    else:
        candidate_ids = retrieve_ads_for_user(
            user=user,
            query=current_message,
            chat_history=chat_history,
            limit=limit * 2
        )
        if not candidate_ids:
            logger.info("No query-based ads found - using fallback")
            candidate_ids = _get_fallback_ads(user, limit * 2)

    if not candidate_ids:
        logger.warning("No ads available (including fallback)")
        return []

    eligible_ids = _apply_frequency_cap(session, candidate_ids, max_impressions=25)
    if not eligible_ids:
        logger.warning("All ads filtered out by frequency capping")
        return []

    ads = list(
        AdvertiserAd.objects.filter(
            id__in=eligible_ids[:limit],
            is_active=True,
            remaining_impressions__gt=0,
            start_date__lte=today,
            end_date__gte=today
        ).select_related('metrics')
    )

    if not ads:
        return []

    _record_impressions(ads, session, request)
    result = _build_ad_result(ads, request)

    logger.info(f"Served {len(result)} ads for session {session.session_id}")
    return result


def _get_fallback_ads_for_new_session(user, session, request, limit=3):
    today = timezone.now().date()

    ad_ids = _get_fallback_ads(user, limit)
    if not ad_ids:
        return []

    ads = list(
        AdvertiserAd.objects.filter(
            id__in=ad_ids,
            is_active=True,
            remaining_impressions__gt=0,
            start_date__lte=today,
            end_date__gte=today
        )
    )
    if not ads:
        return []

    _record_impressions(ads, session, request)
    return _build_ad_result(ads, request)



######################################################################################
# older

# def get_ads_with_tracking(user, session, current_message, chat_history, request, limit=3):
#     """
#     Single function to get ads with complete details and impression tracking
    
#     FIX: Properly handle fallback ads for new sessions
#     """
#     # Get user preferences
#     try:
#         prefs = UserPreference.objects.get(user=user)
#         if prefs.complete_opt_out:
#             return []
#     except UserPreference.DoesNotExist:
#         pass
    
#     # FIX: For first message in session (message_count == 1), use fallback directly
#     # This is more reliable than checking chat_history length
#     if session.message_count <= 1:
#         logger.info(f"First message in session {session.session_id} - using fallback ads")
#         candidate_ids = _get_fallback_ads(user, limit * 2)
#     else:
#         # Get candidate ad IDs from your retrieval system
#         candidate_ids = retrieve_ads_for_user(
#             user=user,
#             query=current_message,
#             chat_history=chat_history,
#             limit=limit * 2  # Get more for filtering
#         )
        
#         # If no query-based results, get fallback ads
#         if not candidate_ids:
#             logger.info("No query-based ads found - using fallback")
#             candidate_ids = _get_fallback_ads(user, limit * 2)
    
#     if not candidate_ids:
#         logger.warning("No ads available (including fallback)")
#         return []
    
#     # Apply frequency capping (max 5 impressions per session)
#     eligible_ids = _apply_frequency_cap(session, candidate_ids, max_impressions=25)
    
#     if not eligible_ids:
#         logger.warning("All ads filtered out by frequency capping")
#         return []
    
#     # Get full ad details
#     ads = AdvertiserAd.objects.filter(
#         id__in=eligible_ids[:limit],
#         is_active=True,
#         remaining_impressions__gt=0,
#         start_date__lte=today,
#         end_date__gte=today
#     ).select_related('metrics')
    
#     result = []
#     for ad in ads:
#         # Record impression using your existing AdEvent system
#         AdEvent.objects.create(ad=ad, event_type="impression")
        
#         # Update metrics using your existing system
#         metrics, _ = AdMetrics.objects.get_or_create(ad=ad)
#         metrics.total_impressions += 1
        
#         # Reduce remaining impressions from ad
#         if ad.remaining_impressions > 0:
#             ad.remaining_impressions -= 1
#             if ad.remaining_impressions <= 0:
#                 ad.is_active = False
#             ad.save(update_fields=['remaining_impressions', 'is_active'])
        
#         # Update spent (0.1 PKR per impression as per your logic)
#         from decimal import Decimal
#         metrics.total_spent += Decimal("0.1")
#         metrics.save()
        
#         # Build click tracking URL
#         click_path = reverse('advertiser:ad-click-redirect', kwargs={'ad_id': ad.id})
#         click_url = request.build_absolute_uri(click_path) if request else click_path
        
#         # Get media URL
#         media_url = None
#         if ad.media_file:
#             try:
#                 media_url = request.build_absolute_uri(ad.media_file.url) if request else ad.media_file.url
#             except:
#                 pass
        
#         result.append({
#             'id': ad.id,
#             'title': ad.title,
#             'description': ad.description,
#             'url': ad.url,  # Original URL
#             'click_url': click_url,  # Tracking URL
#             'media_url': media_url,
#             'category': ad.get_category_display()
#         })
    
#     logger.info(f"Served {len(result)} ads for session {session.session_id}")
#     return result``




# def _get_fallback_ads_for_new_session(user, session, request, limit=3):
#     """Get fallback ads for new session with full tracking"""
#     ad_ids = _get_fallback_ads(user, limit)
    
#     if not ad_ids:
#         return []
    
#     # Build full ad objects with tracking
#     ads = AdvertiserAd.objects.filter(
#         id__in=ad_ids,
#         is_active=True,
#         remaining_impressions__gt=0
#     )
    
#     result = []
#     for ad in ads:
#         # Record impression
#         AdEvent.objects.create(ad=ad, event_type="impression")
        
#         metrics, _ = AdMetrics.objects.get_or_create(ad=ad)
#         metrics.total_impressions += 1
        
#         if ad.remaining_impressions > 0:
#             ad.remaining_impressions -= 1
#             if ad.remaining_impressions <= 0:
#                 ad.is_active = False
#             ad.save(update_fields=['remaining_impressions', 'is_active'])
        
#         from decimal import Decimal
#         metrics.total_spent += Decimal("0.1")
#         metrics.save()
        
#         click_path = reverse('advertiser:ad-click-redirect', kwargs={'ad_id': ad.id})
#         click_url = request.build_absolute_uri(click_path) if request else click_path
        
#         media_url = None
#         if ad.media_file:
#             try:
#                 media_url = request.build_absolute_uri(ad.media_file.url) if request else ad.media_file.url
#             except:
#                 pass
        
#         result.append({
#             'id': ad.id,
#             'title': ad.title,
#             'description': ad.description,
#             'url': ad.url,
#             'click_url': click_url,
#             'media_url': media_url,
#             'category': ad.get_category_display()
#         })
    
#     return result






# def _apply_frequency_cap(session, ad_ids, max_impressions=10):
#     """
#     Apply frequency capping using your AdEvent system
#     Count impressions per ad in current session
#     """
#     from django.db.models import Count
    
#     # Count impressions per ad in this session's timeframe
#     session_start = session.started_at
    
#     impression_counts = {}
#     for ad_id in ad_ids:
#         count = AdEvent.objects.filter(
#             ad_id=ad_id,
#             event_type='impression',
#             timestamp__gte=session_start
#         ).count()
#         impression_counts[ad_id] = count
    
#     # Filter ads below max impressions
#     eligible = [
#         ad_id for ad_id in ad_ids
#         if impression_counts.get(ad_id, 0) < max_impressions
#     ]
    
#     return eligible


