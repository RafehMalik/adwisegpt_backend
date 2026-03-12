
# from django.apps import AppConfig
# import logging

# logger = logging.getLogger(__name__)

# class UserConfig(AppConfig):
#     default_auto_field = 'django.db.models.BigAutoField'
#     name = 'user'

#     def ready(self):
#         """Initialize retrieval system when Django starts"""
#         try:
#             from user.ad_retrieval import get_retrieval_system
            
#             logger.info("Pre-loading Ad Retrieval System...")
#             system = get_retrieval_system()
#             stats = system.get_index_stats()
#             logger.info(f"Retrieval system ready with {stats.get('total_vectors', 0)} ads")
        
#         except Exception as e:
#             logger.error(f"Failed to pre-load retrieval system: {e}")

"""
User App Configuration
Pre-loads ad retrieval system for better performance
"""

from django.apps import AppConfig
import logging
import os

logger = logging.getLogger(__name__)


class UserConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'user'

    def ready(self):
        if os.environ.get('RUN_MAIN') == 'true':
            """
            Called when Django app is ready
            Pre-loads the ad retrieval system for faster first query
            """
            try:
                from user.ad_retrieval import get_retrieval_system
                
                logger.info("Pre-loading Ad Retrieval System...")
                system = get_retrieval_system()
                stats = system.get_index_stats()
                logger.info(
                    f"Ad Retrieval System ready with {stats.get('total_vectors', 0)} ads indexed"
                )
            
            except Exception as e:
                logger.error(f"Failed to pre-load retrieval system: {e}", exc_info=True)
                # Don't raise - app should still start even if retrieval system fails
            # -----------------------------
            # Preload Gemini LLM
            # -----------------------------
            try:
                from user.llm_service import get_llm_service

                logger.info("Pre-loading Gemini LLM service...")
                get_llm_service()   # forces initialization
                logger.info("Gemini LLM service ready")

            except Exception as e:
                logger.error("Failed to initialize Gemini LLM: %s", e, exc_info=True)