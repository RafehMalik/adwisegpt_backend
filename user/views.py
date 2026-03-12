#############################################################  VERSION 2  ########################



# from rest_framework.permissions import AllowAny
# from .utils import send_contact_email, success_response, error_response

# from rest_framework.views import APIView
# from rest_framework.permissions import IsAuthenticated
# from rest_framework import status
# from .models import UserPreference
# from accounts.permissions import IsNormalUser
# from .serializers import UserPreferenceSerializer

# class UserPreferenceView(APIView):
#     permission_classes = [IsAuthenticated, IsNormalUser]

#     def get(self, request):
#         try:
#             preferences, created = UserPreference.objects.get_or_create(user=request.user)
#             serializer = UserPreferenceSerializer(preferences)
#             return success_response(
#                 data=serializer.data,
#                 message="Preferences retrieved successfully.",
#                 status_code=status.HTTP_200_OK
#             )
#         except Exception as e:
#             return error_response(
#                 message="An error occurred while fetching preferences.",
#                 errors=str(e),
#                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

#     def post(self, request):
#         try:
#             preferences, created = UserPreference.objects.get_or_create(user=request.user)
#             serializer = UserPreferenceSerializer(preferences, data=request.data, partial=True)
#             if serializer.is_valid():
#                 serializer.save()
#                 return success_response(
#                     data=serializer.data,
#                     message="Preferences saved successfully.",
#                     status_code=status.HTTP_200_OK
#                 )
#             return error_response(
#                 message="Validation failed.",
#                 errors=serializer.errors,
#                 status_code=status.HTTP_400_BAD_REQUEST
#             )
#         except Exception as e:
#             return error_response(
#                 message="Failed to save preferences.",
#                 errors=str(e),
#                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )


# class ContactUsView(APIView):
#     permission_classes = [AllowAny]

#     def post(self, request):
#         name = request.data.get('name')
#         email = request.data.get('email')
#         subject = request.data.get('subject', 'General Inquiry')
#         message = request.data.get('message')

#         if not all([name, email, message]):
#             return error_response(message="Name, email, and message are required.")

#         if send_contact_email(name, email, subject, message):
#             return success_response(message="Your message has been sent to AdWiseGPT.")

#         return error_response(message="Failed to send email. Please try again later.")


# # ============================================================
# # TEST VIEW
# # ============================================================

# from django.http import JsonResponse
# from django.views import View
# from django.contrib.auth.models import User
# from advertisers.models import AdvertiserAd
# from .ad_retrieval import retrieve_ads_for_user
# import json

# class TestAdRetrievalView(View):
#     def get(self, request):
#         user_id = request.GET.get('user_id')
#         query = request.GET.get('query', 'I need a fast web server')
#         history_raw = request.GET.get('history', '[]')

#         try:
#             chat_history = json.loads(history_raw)
#             user = User.objects.get(id=user_id) if user_id else User.objects.first()
#         except Exception:
#             return JsonResponse({"error": "Invalid user_id or chat history format"}, status=400)

#         ad_ids = retrieve_ads_for_user(
#             user=user,
#             query=query,
#             chat_history=chat_history,
#             limit=3
#         )

#         ads = AdvertiserAd.objects.filter(id__in=ad_ids)
#         ad_data = [
#             {"id": ad.id, "title": ad.title, "category": ad.category,
#              "description": ad.description, "url": ad.url}
#             for ad in ads
#         ]

#         return JsonResponse({
#             "search_query": query,
#             "detected_ad_ids": ad_ids,
#             "retrieved_ads": ad_data,
#             "user_tested": user.username if user else "None"
#         })


# # ============================================================
# # CHAT & ADS VIEWS
# # ============================================================

# from rest_framework.views import APIView
# from rest_framework.permissions import IsAuthenticated
# from rest_framework import status
# from .models import ChatSession, ChatMessage
# from .serializers import ChatMessageSerializer, SessionSerializer
# from .utils import success_response, error_response, get_ads_with_tracking
# from accounts.permissions import IsNormalUser
# import uuid
# import logging

# logger = logging.getLogger(__name__)

# import asyncio
# import uuid
# from adrf.views import APIView
# from asgiref.sync import sync_to_async
# from django.db.models import F
# import time

# class ChatView(APIView):
#     """
#     Endpoint 1 - POST /chat/
#     Handles ONLY the LLM conversation. No ad logic.
#     Receives: message, session_id
#     Returns:  session_id, messages (text only)
#     """
#     permission_classes = [IsNormalUser]

#     async def post(self, request):
#         message    = request.data.get('message')
#         session_id = request.data.get('session_id')

#         if not message:
#             return error_response(
#                 message="Message is required",
#                 status_code=status.HTTP_400_BAD_REQUEST
#             )

#         try:
#             # Step 1: Get or create session
#             session = await self._get_or_create_session(request.user, session_id, message)

#             # Step 2: Fetch history BEFORE saving the current user message.
#             # FIX 1: Previously history was fetched concurrently with _save_message,
#             # creating a race condition where the freshly saved user message could
#             # be missing from the history passed to the LLM. Fetch first, then save.
#             chat_history = await self._get_chat_history(session)
            
#             # Step 3: Save user message + increment count concurrently.
#             # These two ops don't depend on each other, so parallel is fine.
#             await asyncio.gather(
#                 self._save_message(session, 'user', message),
#                 self._increment_session_count(session),
#             )

#             # Step 4: LLM call — still uses sync_to_async wrapping the existing
#             # llm_service (unchanged). This is still the main latency source.
#             assistant_response = await self._generate_ai_response(
#                 user_message=message,
#                 session=session,
#                 chat_history=chat_history,
#             )
            

#             # Step 5: Save assistant response
#             await self._save_message(session, 'assistant', assistant_response)

#             # Step 6: Build final message list without an extra DB query.
#             # FIX 2: Previously called _get_final_messages() which fired a full
#             # SELECT after the LLM response was already saved. We now build the
#             # response payload from the in-memory history dicts + the two new
#             # messages, saving one round-trip to the DB.
#             messages = self._build_response_payload(chat_history, message, assistant_response)
           
#             return success_response(
#                 data={
#                     'session_id': session.session_id,
#                     'messages':   messages,
#                 },
#                 message="Message sent successfully",
#                 status_code=status.HTTP_200_OK,
#             )

#         except Exception as e:
#             logger.error(f"Chat error: {str(e)}", exc_info=True)
#             return error_response(
#                 message="Failed to process message",
#                 errors=str(e),
#                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             )

#     # ------------------------------------------------------------------ #
#     #  Session                                                             #
#     # ------------------------------------------------------------------ #

#     async def _get_or_create_session(self, user, session_id, first_message):
#         def _query():
#             if session_id:
#                 session = ChatSession.objects.filter(
#                     session_id=session_id, user=user, is_active=True
#                 ).first()
#                 if session:
#                     return session

#             title = first_message[:50] + '...' if len(first_message) > 50 else first_message
#             return ChatSession.objects.create(
#                 user=user,
#                 session_id=f"session_{uuid.uuid4().hex[:16]}",
#                 title=title,
#             )

#         return await sync_to_async(_query)()

#     async def _increment_session_count(self, session):
#         """Atomic increment — avoids race conditions from read-modify-write."""
#         await sync_to_async(
#             lambda: ChatSession.objects.filter(pk=session.pk).update(
#                 message_count=F('message_count') + 1
#             )
#         )()
#         session.message_count += 1  # keep in-memory object consistent

#     async def _save_message(self, session, message_type, content):
#         return await sync_to_async(ChatMessage.objects.create)(
#             session=session,
#             message_type=message_type,
#             content=content,
#         )

#     # ------------------------------------------------------------------ #
#     #  History                                                             #
#     # ------------------------------------------------------------------ #

#     MAX_HISTORY_TOKENS = 70_000
#     CHARS_PER_TOKEN    = 4
#     MAX_HISTORY_CHARS  = MAX_HISTORY_TOKENS * CHARS_PER_TOKEN  # 280_000 chars

#     async def _get_chat_history(self, session):
#         all_messages = await sync_to_async(
#             lambda: list(
#                 ChatMessage.objects.filter(session=session).order_by('timestamp')
#             )
#         )()

#         if not all_messages:
#             return []

#         kept        = []
#         total_chars = 0

#         for msg in reversed(all_messages):
#             msg_chars = len(msg.content)
#             if total_chars + msg_chars > self.MAX_HISTORY_CHARS:
#                 break
#             kept.append(msg)
#             total_chars += msg_chars

#         kept.reverse()

#         skipped = len(all_messages) - len(kept)
#         if skipped:
#             logger.info(
#                 f"Session {session.session_id}: history trimmed — "
#                 f"kept {len(kept)}/{len(all_messages)} messages "
#                 f"({total_chars:,} chars ≈ {total_chars // self.CHARS_PER_TOKEN:,} tokens); "
#                 f"dropped {skipped} oldest messages."
#             )

#         return [
#             {'role': msg.message_type, 'content': msg.content}
#             for msg in kept
#         ]

#     def _build_response_payload(self, chat_history, user_message, assistant_response):
#         """
#         FIX 2: Build the final messages list from in-memory data instead of
#         re-querying the DB. chat_history already contains all previous messages
#         as dicts; we just append the two new turns.

#         Note: this returns plain dicts. If your client needs extra fields that
#         only exist on DB rows (e.g. id, timestamp), replace this with a targeted
#         fetch of the last 2 rows — still far cheaper than fetching everything.
#         """
#         messages = list(chat_history)  # copy so we don't mutate the original
#         messages.append({'role': 'user',      'content': user_message})
#         messages.append({'role': 'assistant', 'content': assistant_response})
#         return messages

#     # ------------------------------------------------------------------ #
#     #  LLM                                                                 #
#     # ------------------------------------------------------------------ #

#     async def _generate_ai_response(self, user_message, session, chat_history):
#         """
#         Calls the existing llm_service unchanged, wrapped in sync_to_async.
#         The thread-pool overhead is minimal; the real latency is Gemini's
#         network round-trip (~3-8s) which cannot be reduced from the view side
#         without changing llm_service to use generate_content_async().
#         """
#         try:
#             from .llm_service import generate_chat_response

#             response = await sync_to_async(generate_chat_response)(
#                 user_message=user_message,
#                 chat_history=chat_history,
#                 session_id=session.session_id,
#             )
#             return response

#         except Exception as e:
#             logger.error(f"LLM generation failed: {e}", exc_info=True)
#             return (
#                 f"Thank you for your message. I understand you're asking about: "
#                 f"'{user_message[:100]}'. Could you provide more details?"
#             )



# # ###################### async version for chat ads
# class ChatAdsView(APIView):
#     """
#     Endpoint 2 - POST /chat/ads/
#     Handles ONLY ad refresh logic. No LLM call.
#     Receives: session_id, message (used as retrieval query)
#     Returns:  sponsored_ads, ads_refreshed, refresh_reason

#     The frontend should call this in parallel with (or right after) /chat/,
#     then display the ads panel independently.
#     """
#     permission_classes = [IsAuthenticated, IsNormalUser]

#     MESSAGES_BEFORE_AD_REFRESH = 2

#     async def post(self, request):
#         session_id = request.data.get("session_id")
#         message = request.data.get("message", "")
#         force_refresh = request.data.get("force_refresh", False)

#         if not session_id:
#             return error_response(
#                 message="session_id is required",
#                 status_code=status.HTTP_400_BAD_REQUEST
#             )

#         try:
#             session = await ChatSession.objects.aget(
#                 session_id=session_id,
#                 user=request.user,
#                 is_active=True
#             )
           

#             current_count = session.message_count
#             last_2_user_messages = await self._get_last_user_messages(session, limit=2)
            

#             should_refresh = await self._should_refresh_ads(
#                 session=session,
#                 current_message=message,
#                 chat_history=last_2_user_messages,  # only last 2 user msgs for intent detection
#                 force_refresh=force_refresh,
#                 current_count=current_count
#             )
            

#             ads = []
#             refresh_reason = "none"

#             if should_refresh["refresh"]:
#                 chat_history = await self._get_plain_history(session)
#                 ads = await sync_to_async(get_ads_with_tracking)(
#                     user=request.user,
#                     session=session,
#                     current_message=message,
#                     chat_history=chat_history,  # full history for ad retrieval
#                     request=request,
#                     limit=3
#                 )
#                 session.last_ad_refresh_count = session.message_count
#                 await session.asave()
#                 refresh_reason = should_refresh["reason"]

#             return success_response(
#                 data={
#                     "session_id": session.session_id,
#                     "sponsored_ads": ads,
#                     "ads_refreshed": should_refresh["refresh"],
#                     "refresh_reason": refresh_reason,
#                 },
#                 message="Ads fetched successfully",
#                 status_code=status.HTTP_200_OK,
#             )

#         except ChatSession.DoesNotExist:
#             return error_response(
#                 message="Session not found",
#                 status_code=status.HTTP_404_NOT_FOUND
#             )
#         except Exception as e:
#             logger.error(f"Ads fetch error: {str(e)}")
#             return error_response(
#                 message="Failed to fetch ads",
#                 errors=str(e),
#                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

#     async def _should_refresh_ads(self, session, current_message, chat_history, force_refresh, current_count):
#         if force_refresh:
#             return {"refresh": True, "reason": "manual_refresh"}

#         if current_count <= 1:
#             return {"refresh": True, "reason": "first_message"}

#         messages_since_refresh = session.message_count - session.last_ad_refresh_count
#         if messages_since_refresh >= self.MESSAGES_BEFORE_AD_REFRESH:
#             return {"refresh": True, "reason": "message_count"}

#         from .utils import detect_intent_shift
#         intent_shifted = await sync_to_async(detect_intent_shift)(current_message, chat_history)
#         if intent_shifted:
#             return {"refresh": True, "reason": "intent_shift"}

#         return {"refresh": False, "reason": "none"}

#     async def _get_plain_history(self, session, limit=30):
#         """Full plain text history for ad retrieval context."""
#         messages = ChatMessage.objects.filter(
#             session=session
#         ).order_by("-timestamp")[:limit]
#         return [m.content async for m in messages.aiterator()][::-1]

#     async def _get_last_user_messages(self, session, limit=2):
#         """Last N user messages for intent-shift detection."""
#         messages = ChatMessage.objects.filter(
#             session=session,
#             message_type="user"
#         ).order_by("-timestamp")[:limit]
#         return [m.content async for m in messages.aiterator()][::-1]


# # ============================================================
# # SESSION VIEWS
# # ============================================================

# import asyncio
# import uuid
# from adrf.views import APIView
# from asgiref.sync import sync_to_async

# class NewChatView(APIView):
#     permission_classes = [IsAuthenticated, IsNormalUser]

#     async def post(self, request):
#         try:
#             # Create session and fetch initial ads concurrently
#             session = await sync_to_async(ChatSession.objects.create)(
#                 user=request.user,
#                 session_id=f"session_{uuid.uuid4().hex[:16]}",
#                 title="New Chat"
#             )

#             ads = await self._get_initial_ads(request.user, session, request)

#             return success_response(
#                 data={
#                     'session_id':     session.session_id,
#                     'title':          session.title,
#                     'sponsored_ads':  ads,
#                     'ads_refreshed':  True,
#                     'refresh_reason': 'new_session'
#                 },
#                 message="New chat created successfully",
#                 status_code=status.HTTP_201_CREATED
#             )

#         except Exception as e:
#             logger.error(f"New chat error: {e}")
#             return error_response(
#                 message="Failed to create new chat",
#                 errors=str(e),
#                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

#     async def _get_initial_ads(self, user, session, request):
#         from .utils import get_ads_with_tracking, _get_fallback_ads_for_new_session

#         # Fetch previous messages from other sessions asynchronously
#         get_previous_messages = sync_to_async(
#             lambda: list(
#                 ChatMessage.objects.filter(
#                     session__user=user, message_type='user', session__is_active=True
#                 ).order_by('-timestamp')[:10]
#             )
#         )
#         previous_messages = await get_previous_messages()
#         chat_history = [msg.content for msg in reversed(previous_messages)]

#         if chat_history:
#             ads = await sync_to_async(get_ads_with_tracking)(
#                 user=user, session=session, current_message=chat_history[-1],
#                 chat_history=chat_history[:-1], request=request, limit=3
#             )
#             if ads:
#                 return ads
#         logger.info("fallback ads trigering")
#         return await sync_to_async(_get_fallback_ads_for_new_session)(
#             user=user, session=session, request=request, limit=3
#         )

# class SessionListView(APIView):
#     permission_classes = [IsAuthenticated, IsNormalUser]

#     def get(self, request):
#         try:
#             sessions = ChatSession.objects.filter(
#                 user=request.user, is_active=True
#             ).order_by('-last_activity')

#             data = []
#             for session in sessions:
#                 last_msg = session.messages.filter(message_type='user').last()
#                 preview = ''
#                 if last_msg:
#                     preview = last_msg.content[:50]
#                     if len(last_msg.content) > 50:
#                         preview += '...'

#                 data.append({
#                     'session_id': session.session_id,
#                     'title': session.title,
#                     'last_activity': session.last_activity,
#                     'message_count': session.message_count,
#                     'last_message_preview': preview
#                 })

#             return success_response(data={'sessions': data}, message="Sessions retrieved successfully")

#         except Exception as e:
#             return error_response(
#                 message="Failed to retrieve sessions",
#                 errors=str(e),
#                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )



# class SessionDetailView(APIView):
#     permission_classes = [IsAuthenticated, IsNormalUser]

#     async def get(self, request, session_id):
#         try:
#             session = await sync_to_async(
#                 ChatSession.objects.get
#             )(session_id=session_id, user=request.user, is_active=True)

#             # Run messages fetching and ads retrieval concurrently
#             messages, ads = await asyncio.gather(
#                 self._get_session_messages(session),
#                 self._get_session_ads(request.user, session, request)
#             )

#             return success_response(
#                 data={
#                     'session_id': session.session_id,
#                     'title': session.title,
#                     'messages': await sync_to_async(
#                         lambda: ChatMessageSerializer(messages, many=True).data
#                     )(),
#                     'sponsored_ads': ads,
#                     'ads_refreshed': False
#                 },
#                 message="Session retrieved successfully"
#             )

#         except ChatSession.DoesNotExist:
#             return error_response(message="Session not found", status_code=status.HTTP_404_NOT_FOUND)
#         except Exception as e:
#             return error_response(
#                 message="Failed to retrieve session",
#                 errors=str(e),
#                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

#     async def _get_session_messages(self, session):
#         """Fetch chat messages asynchronously."""
#         get_messages = sync_to_async(
#             lambda: list(
#                 ChatMessage.objects.filter(session=session).order_by('timestamp')
#             )
#         )
#         return await get_messages()

#     async def _get_session_ads(self, user, session, request):
#         """Fetch ads asynchronously."""
#         from .utils import get_ads_with_tracking, _get_fallback_ads_for_new_session

#         get_user_messages = sync_to_async(
#             lambda: list(
#                 ChatMessage.objects.filter(
#                     session=session, message_type='user'
#                 ).order_by('timestamp')[:10]
#             )
#         )
#         messages = await get_user_messages()
#         chat_history = [msg.content for msg in messages]

#         if chat_history:
#             last_message = chat_history[-1]
#             ads = await sync_to_async(get_ads_with_tracking)(
#                 user=user, session=session, current_message=last_message,
#                 chat_history=chat_history[:-1], request=request, limit=3
#             )
#             if ads:
#                 return ads

#         return await sync_to_async(_get_fallback_ads_for_new_session)(
#             user, session, request, limit=3
#         )
    
# class RefreshAdsView(APIView):
#     permission_classes = [IsAuthenticated, IsNormalUser]

#     async def post(self, request):
#         session_id = request.data.get('session_id')

#         if not session_id:
#             return error_response(
#                 message="Session ID is required",
#                 status_code=status.HTTP_400_BAD_REQUEST
#             )

#         try:
#             session = await ChatSession.objects.aget(
#                 session_id=session_id, user=request.user, is_active=True
#             )

#             # Single query — fetch last 10 messages, derive both chat_history
#             # and current_message from the same result set
#             messages = await sync_to_async(
#                 lambda: list(
#                     ChatMessage.objects.filter(session=session)
#                     .order_by('-timestamp')[:10]
#                 )
#             )()

#             # Reverse for chronological order
#             messages_chrono = list(reversed(messages))
#             chat_history = [m.content for m in messages_chrono]

#             # Last user message from the already-fetched list — no extra query
#             last_user_message = next(
#                 (m for m in reversed(messages_chrono) if m.message_type == 'user'),
#                 None
#             )
#             current_message = last_user_message.content if last_user_message else ""

#             ads = await sync_to_async(get_ads_with_tracking)(
#                 user=request.user,
#                 session=session,
#                 current_message=current_message,
#                 chat_history=chat_history,
#                 request=request,
#                 limit=3
#             )

#             session.last_ad_refresh_count = session.message_count
#             await session.asave()

#             return success_response(
#                 data={
#                     'session_id':     session.session_id,
#                     'sponsored_ads':  ads,
#                     'refresh_reason': 'manual_refresh',
#                 },
#                 message="Ads refreshed successfully"
#             )

#         except ChatSession.DoesNotExist:
#             return error_response(
#                 message="Session not found",
#                 status_code=status.HTTP_404_NOT_FOUND
#             )
#         except Exception as e:
#             logger.error(f"Refresh ads error: {str(e)}")
#             return error_response(
#                 message="Failed to refresh ads",
#                 errors=str(e),
#                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

########################################################################## views with cahche
"""
views.py — full integration with SessionHistoryCache
=====================================================
Drop-in replacement. Requires session_history_cache.py in the same app directory.
"""

# ============================================================
# IMPORTS
# ============================================================

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from django.http import JsonResponse
from django.views import View
from django.contrib.auth.models import User
from django.db.models import F

import asyncio 
import uuid
import json
import logging

from adrf.views import APIView
from asgiref.sync import sync_to_async

from accounts.permissions import IsNormalUser
from advertisers.models import AdvertiserAd

from .models import UserPreference, ChatSession, ChatMessage
from .serializers import UserPreferenceSerializer, ChatMessageSerializer, SessionSerializer
from .utils import (
    send_contact_email, success_response, error_response,
    get_ads_with_tracking, detect_intent_shift,
)
from .ad_retrieval import retrieve_ads_for_user
from .session_history_cache import history_cache   # ← the shared singleton
from django.http import StreamingHttpResponse


from .throttle import (
    ChatUserMinuteThrottle, ChatUserDailyThrottle,
    AdsUserThrottle, NewChatThrottle,
    RefreshAdsThrottle, ContactAnonThrottle,
)

logger = logging.getLogger(__name__)


# ============================================================
# USER PREFERENCE VIEWS
# ============================================================

class UserPreferenceView(APIView):
    permission_classes = [IsAuthenticated, IsNormalUser]

    def get(self, request):
        try:
            preferences, created = UserPreference.objects.get_or_create(user=request.user)
            serializer = UserPreferenceSerializer(preferences)
            return success_response(
                data=serializer.data,
                message="Preferences retrieved successfully.",
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            return error_response(
                message="An error occurred while fetching preferences.",
                errors=str(e),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        try:
            preferences, created = UserPreference.objects.get_or_create(user=request.user)
            serializer = UserPreferenceSerializer(preferences, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return success_response(
                    data=serializer.data,
                    message="Preferences saved successfully.",
                    status_code=status.HTTP_200_OK
                )
            return error_response(
                message="Validation failed.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return error_response(
                message="Failed to save preferences.",
                errors=str(e),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ============================================================
# CONTACT VIEW
# ============================================================

class ContactUsView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ContactAnonThrottle]

    def post(self, request):
        name    = request.data.get('name')
        email   = request.data.get('email')
        subject = request.data.get('subject', 'General Inquiry')
        message = request.data.get('message')

        if not all([name, email, message]):
            return error_response(message="Name, email, and message are required.")

        if send_contact_email(name, email, subject, message):
            return success_response(message="Your message has been sent to AdWiseGPT.")

        return error_response(message="Failed to send email. Please try again later.")


# ============================================================
# TEST VIEW
# ============================================================

class TestAdRetrievalView(View):
    def get(self, request):
        user_id     = request.GET.get('user_id')
        query       = request.GET.get('query', 'I need a fast web server')
        history_raw = request.GET.get('history', '[]')

        try:
            chat_history = json.loads(history_raw)
            user = User.objects.get(id=user_id) if user_id else User.objects.first()
        except Exception:
            return JsonResponse({"error": "Invalid user_id or chat history format"}, status=400)

        ad_ids = retrieve_ads_for_user(
            user=user, query=query, chat_history=chat_history, limit=3
        )
        ads = AdvertiserAd.objects.filter(id__in=ad_ids)
        ad_data = [
            {"id": ad.id, "title": ad.title, "category": ad.category,
             "description": ad.description, "url": ad.url}
            for ad in ads
        ]
        return JsonResponse({
            "search_query":    query,
            "detected_ad_ids": ad_ids,
            "retrieved_ads":   ad_data,
            "user_tested":     user.username if user else "None"
        })


# ============================================================
# CHAT VIEW  (LLM only — no ad logic)
# ============================================================

class ChatView(APIView):
    """
    POST /chat/
    Handles ONLY the LLM conversation.
    Receives: message, session_id
    Returns:  session_id, messages (text only)

    Cache integration
    -----------------
    • history_cache.get_history_async()  — replaces _get_chat_history() DB query.
    • history_cache.async_append()       — keeps the cache current after every save.
    • New sessions are pre-warmed with [] so the first get_history_async() is free.
    """
    permission_classes = [IsNormalUser,IsAuthenticated]
    throttle_classes = [ChatUserMinuteThrottle]

    async def post(self, request):
        message    = request.data.get('message')
        session_id = request.data.get('session_id')

        if not message:
            return error_response(
                message="Message is required",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Step 1: Get or create session (new sessions are cache-warmed inside)
            session = await self._get_or_create_session(request.user, session_id, message)

            # Step 2: Fetch history from cache (DB only on first-ever access)
            chat_history = await history_cache.get_history_async(session.session_id)
            
            # Step 3: Persist user message + increment count concurrently,
            #         then mirror both into the cache.
            await asyncio.gather(
                self._save_message(session, 'user', message),
                self._increment_session_count(session),
            )
            await history_cache.async_append(session.session_id, 'user', message)

            # Step 4: LLM call (main latency — Gemini network round-trip)
        #orignal response
            assistant_response = await self._generate_ai_response(
                user_message=message,
                session=session,
                chat_history=chat_history,
            )
           
            #Step 5: Persist assistant response + mirror into cache
            await self._save_message(session, 'assistant', assistant_response)
            await history_cache.async_append(session.session_id, 'assistant', assistant_response)

            # Step 6: Build payload from in-memory data — zero extra DB query
            messages = self._build_response_payload(chat_history, message, assistant_response)

#older response
            return success_response(
                data={
                    'session_id': session.session_id,
                    'message':   assistant_response,
                },
                message="Message sent successfully",
                status_code=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Chat error: {str(e)}", exc_info=True)
            return error_response(
                message="Failed to process message",
                errors=str(e),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ------------------------------------------------------------------ #
    #  Session helpers                                                     #
    # ------------------------------------------------------------------ #

    async def _get_or_create_session(self, user, session_id, first_message):
        def _query():
            if session_id:
                session = ChatSession.objects.filter(
                    session_id=session_id, user=user, is_active=True
                ).first()
                if session:
                    return session

            title = first_message[:50] + ('...' if len(first_message) > 50 else '')
            new_session = ChatSession.objects.create(
                user=user,
                session_id=f"session_{uuid.uuid4().hex[:16]}",
                title=title,
            )
            # Pre-warm cache so first get_history_async() skips the DB entirely
            history_cache.warm(new_session.session_id, [])
            return new_session

        return await sync_to_async(_query)()

    async def _increment_session_count(self, session):
        """Atomic increment — avoids read-modify-write race conditions."""
        await sync_to_async(
            lambda: ChatSession.objects.filter(pk=session.pk).update(
                message_count=F('message_count') + 1
            )
        )()
        session.message_count += 1  # keep in-memory object consistent

    async def _save_message(self, session, message_type, content):
        return await sync_to_async(ChatMessage.objects.create)(
            session=session,
            message_type=message_type,
            content=content,
        )

    # ------------------------------------------------------------------ #
    #  Payload builder                                                     #
    # ------------------------------------------------------------------ #

    def _build_response_payload(self, chat_history, user_message, assistant_response):
        """
        Build the final messages list purely from in-memory data.
        chat_history = messages *before* this turn; we append the two new turns.
        """
        messages = list(chat_history)
        messages.append({'role': 'user',      'content': user_message})
        messages.append({'role': 'assistant', 'content': assistant_response})
        return messages

    # ------------------------------------------------------------------ #
    #  LLM                                                                 #
    # ------------------------------------------------------------------ #

    async def _generate_ai_response(self, user_message, session, chat_history):
        try:
            from .llm_service import generate_chat_response

            response = await sync_to_async(generate_chat_response)(
                user_message=user_message,
                chat_history=chat_history,
                session_id=session.session_id,
            )
            return response

        except Exception as e:
            logger.error(f"LLM generation failed: {e}", exc_info=True)
            return (
                f"Thank you for your message. I understand you're asking about: "
                f"'{user_message[:100]}'. Could you provide more details?"
            )


# ============================================================
# CHAT ADS VIEW  (ad refresh only — no LLM)
# ============================================================

class ChatAdsView(APIView):
    """
    POST /chat/ads/
    Handles ONLY ad refresh logic. No LLM call.
    Receives: session_id, message (retrieval query), force_refresh
    Returns:  sponsored_ads, ads_refreshed, refresh_reason

    Cache integration
    -----------------
    • history_cache.get_history_async()  — replaces both _get_plain_history()
      and _get_last_user_messages() DB queries.
    • All slicing/filtering is done on the in-memory list.
    """
    permission_classes = [IsAuthenticated, IsNormalUser]
    throttle_classes = [AdsUserThrottle]

    MESSAGES_BEFORE_AD_REFRESH = 2

    async def post(self, request):
        session_id    = request.data.get("session_id")
        message       = request.data.get("message", "")
        force_refresh = request.data.get("force_refresh", False)

        if not session_id:
            return error_response(
                message="session_id is required",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            session = await ChatSession.objects.aget(
                session_id=session_id, user=request.user, is_active=True
            )

            current_count = session.message_count

            # Pull full history from cache — zero DB query on warm cache
            all_history = await history_cache.get_history_async(session_id)

            # Last 2 user messages for intent-shift detection (in-memory slice)
            last_2_user_msgs = [
                m["content"] for m in all_history if m["role"] == "user"
            ][-2:]

            should_refresh = await self._should_refresh_ads(
                session=session,
                current_message=message,
                chat_history=last_2_user_msgs,
                force_refresh=force_refresh,
                current_count=current_count,
            )

            ads           = []
            refresh_reason = "none"

            if should_refresh["refresh"]:
                # Full plain-text history for ad retrieval — from cache, no DB
                chat_history_plain = [m["content"] for m in all_history]

                ads = await sync_to_async(get_ads_with_tracking)(
                    user=request.user,
                    session=session,
                    current_message=message,
                    chat_history=chat_history_plain,
                    request=request,
                    limit=3,
                )
                session.last_ad_refresh_count = session.message_count
                await session.asave()
                refresh_reason = should_refresh["reason"]

            return success_response(
                data={
                    "session_id":     session.session_id,
                    "sponsored_ads":  ads,
                    "ads_refreshed":  should_refresh["refresh"],
                    "refresh_reason": refresh_reason,
                },
                message="Ads fetched successfully",
                status_code=status.HTTP_200_OK,
            )

        except ChatSession.DoesNotExist:
            return error_response(
                message="Session not found",
                status_code=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Ads fetch error: {str(e)}")
            return error_response(
                message="Failed to fetch ads",
                errors=str(e),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def _should_refresh_ads(self, session, current_message, chat_history,
                                   force_refresh, current_count):
        if force_refresh:
            return {"refresh": True, "reason": "manual_refresh"}

        if current_count <= 1:
            return {"refresh": True, "reason": "first_message"}

        messages_since_refresh = session.message_count - session.last_ad_refresh_count
        if messages_since_refresh >= self.MESSAGES_BEFORE_AD_REFRESH:
            return {"refresh": True, "reason": "message_count"}

        intent_shifted = await sync_to_async(detect_intent_shift)(
            current_message, chat_history
        )
        if intent_shifted:
            return {"refresh": True, "reason": "intent_shift"}

        return {"refresh": False, "reason": "none"}


# ============================================================
# SESSION VIEWS
# ============================================================

class NewChatView(APIView):
    """
    POST /chat/new/
    Creates a fresh session and returns initial ads.

    Cache integration
    -----------------
    • async_warm(session_id, []) pre-populates the cache so the very first
      get_history_async() call for this session costs zero DB queries.
    """
    permission_classes = [IsAuthenticated, IsNormalUser]
    throttle_classes = [NewChatThrottle]

    async def post(self, request):
        try:
            session = await sync_to_async(ChatSession.objects.create)(
                user=request.user,
                session_id=f"session_{uuid.uuid4().hex[:16]}",
                title="New Chat",
            )
            # Pre-warm so any view hitting this session_id skips the cold-load
            await history_cache.async_warm(session.session_id, [])

            ads = await self._get_initial_ads(request.user, session, request)

            return success_response(
                data={
                    'session_id':     session.session_id,
                    'title':          session.title,
                    'sponsored_ads':  ads,
                    'ads_refreshed':  True,
                    'refresh_reason': 'new_session',
                },
                message="New chat created successfully",
                status_code=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"New chat error: {e}")
            return error_response(
                message="Failed to create new chat",
                errors=str(e),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def _get_initial_ads(self, user, session, request):
        from .utils import get_ads_with_tracking, _get_fallback_ads_for_new_session

        # Fetch recent messages from *other* sessions to seed ad relevance
        get_previous_messages = sync_to_async(
            lambda: list(
                ChatMessage.objects.filter(
                    session__user=user, message_type='user', session__is_active=True
                ).order_by('-timestamp')[:10]
            )
        )
        previous_messages = await get_previous_messages()
        chat_history = [msg.content for msg in reversed(previous_messages)]

        if chat_history:
            ads = await sync_to_async(get_ads_with_tracking)(
                user=user, session=session, current_message=chat_history[-1],
                chat_history=chat_history[:-1], request=request, limit=3,
            )
            if ads:
                return ads

        logger.info("Fallback ads triggering for new session")
        return await sync_to_async(_get_fallback_ads_for_new_session)(
            user=user, session=session, request=request, limit=3
        )


class SessionListView(APIView):
    """GET /chat/sessions/ — list all active sessions for the user."""
    permission_classes = [IsAuthenticated, IsNormalUser]

    def get(self, request):
        try:
            sessions = ChatSession.objects.filter(
                user=request.user, is_active=True
            ).order_by('-last_activity')

            data = []
            for session in sessions:
                last_msg = session.messages.filter(message_type='user').last()
                preview  = ''
                if last_msg:
                    preview = last_msg.content[:50]
                    if len(last_msg.content) > 50:
                        preview += '...'

                data.append({
                    'session_id':           session.session_id,
                    'title':                session.title,
                    'last_activity':        session.last_activity,
                    'message_count':        session.message_count,
                    'last_message_preview': preview,
                })

            return success_response(
                data={'sessions': data},
                message="Sessions retrieved successfully"
            )

        except Exception as e:
            return error_response(
                message="Failed to retrieve sessions",
                errors=str(e),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SessionDetailView(APIView):
    """
    GET /chat/sessions/<session_id>/
    Returns full message history + current ads for a session.

    Cache integration
    -----------------
    • history_cache.get_history_async() supplies the content needed for ad
      retrieval — no extra DB query.
    • _get_session_messages() still runs once for serialization (we need
      id + timestamp from the DB rows for the client).
    • Both run concurrently via asyncio.gather().
    """
    permission_classes = [IsAuthenticated, IsNormalUser]

    async def get(self, request, session_id):
        try:
            session = await sync_to_async(ChatSession.objects.get)(
                session_id=session_id, user=request.user, is_active=True
            )

            # Run DB fetch (for serialization) and cache read concurrently
            db_messages, history_dicts = await asyncio.gather(
                self._get_session_messages(session),
                history_cache.get_history_async(session_id),
            )

            ads = await self._get_session_ads_from_cache(
                request.user, session, request, history_dicts
            )

            return success_response(
                data={
                    'session_id':    session.session_id,
                    'title':         session.title,
                    'messages':      await sync_to_async(
                                         lambda: ChatMessageSerializer(db_messages, many=True).data
                                     )(),
                    'sponsored_ads': ads,
                    'ads_refreshed': False,
                },
                message="Session retrieved successfully"
            )

        except ChatSession.DoesNotExist:
            return error_response(
                message="Session not found",
                status_code=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return error_response(
                message="Failed to retrieve session",
                errors=str(e),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    async def _get_session_messages(self, session):
        """DB fetch — needed for id/timestamp fields in the serialized response."""
        return await sync_to_async(
            lambda: list(
                ChatMessage.objects.filter(session=session).order_by('timestamp')
            )
        )()

    async def _get_session_ads_from_cache(self, user, session, request, history_dicts):
        """
        Ad retrieval using cached history dicts — replaces the old
        _get_session_ads() which issued a separate DB query.
        """
        from .utils import get_ads_with_tracking, _get_fallback_ads_for_new_session

        user_messages = [m["content"] for m in history_dicts if m["role"] == "user"]

        if user_messages:
            ads = await sync_to_async(get_ads_with_tracking)(
                user=user, session=session,
                current_message=user_messages[-1],
                chat_history=user_messages[:-1],
                request=request, limit=3,
            )
            if ads:
                return ads

        return await sync_to_async(_get_fallback_ads_for_new_session)(
            user, session, request, limit=3
        )


class RefreshAdsView(APIView):
    """
    POST /chat/ads/refresh/
    Manually refresh the ad panel for a session.

    Cache integration
    -----------------
    • history_cache.get_history_async() replaces the 10-message DB query.
    • last_user_message is derived from the in-memory list — no extra query.
    """
    permission_classes = [IsAuthenticated, IsNormalUser]
    throttle_classes = [RefreshAdsThrottle]

    async def post(self, request):
        session_id = request.data.get('session_id')

        if not session_id:
            return error_response(
                message="Session ID is required",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            session = await ChatSession.objects.aget(
                session_id=session_id, user=request.user, is_active=True
            )

            # Full history from cache — zero DB query on warm cache
            all_history  = await history_cache.get_history_async(session_id)
            chat_history = [m["content"] for m in all_history]

            # Last user message derived from the in-memory list
            last_user_msg = next(
                (m["content"] for m in reversed(all_history) if m["role"] == "user"),
                ""
            )

            ads = await sync_to_async(get_ads_with_tracking)(
                user=request.user,
                session=session,
                current_message=last_user_msg,
                chat_history=chat_history,
                request=request,
                limit=3,
            )

            session.last_ad_refresh_count = session.message_count
            await session.asave()

            return success_response(
                data={
                    'session_id':     session.session_id,
                    'sponsored_ads':  ads,
                    'refresh_reason': 'manual_refresh',
                },
                message="Ads refreshed successfully"
            )

        except ChatSession.DoesNotExist:
            return error_response(
                message="Session not found",
                status_code=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Refresh ads error: {str(e)}")
            return error_response(
                message="Failed to refresh ads",
                errors=str(e),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )