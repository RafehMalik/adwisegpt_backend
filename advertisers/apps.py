

"""
Advertisers App Configuration
Integrates APScheduler for automatic ad expiry management
"""

from django.apps import AppConfig
import logging
import os

logger = logging.getLogger(__name__)


class AdvertisersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'advertisers'

    def ready(self):
        if os.environ.get('RUN_MAIN') == 'true':
            """
            Called when Django app is ready
            - Imports signals
            - Starts APScheduler for ad expiry management
            """
            # 1. Import signals (keep existing behavior)
            import advertisers.signals
            
            # 2. Start ad expiry scheduler
            try:
                from advertisers.ad_expiry_scheduler import start_scheduler,get_scheduler
                
                logger.info("Starting Ad Expiry Scheduler...")
                start_scheduler()
                logger.info("Ad Expiry Scheduler started successfully")
                logger.info("Running startup expiry check...")
                get_scheduler().force_check_now()
                logger.info("Startup expiry check completed")

                
            
            except Exception as e:
                logger.error(f"Failed to start Ad Expiry Scheduler: {e}", exc_info=True)
            
            # Note: Removed the manual expiry check on startup
            # The scheduler will handle this automatically