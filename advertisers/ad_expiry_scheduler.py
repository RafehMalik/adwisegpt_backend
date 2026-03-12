"""
APScheduler Service for Ad Expiry Management
Handles:
- Daily expiry checks for ads
- Automatic deactivation of expired ads
- Removal from Pinecone vector database
- Logging and monitoring
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.utils import timezone
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class AdExpiryScheduler:
    """
    Background scheduler for ad expiry management
    Runs daily at midnight to check and deactivate expired ads
    """
    
    _instance = None
    _scheduler = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._scheduler is not None:
            return
        
        self._scheduler = BackgroundScheduler(
            timezone=settings.TIME_ZONE if hasattr(settings, 'TIME_ZONE') else 'UTC'
        )
        
        logger.info("Ad Expiry Scheduler initialized")
    
    def start(self):
        """Start the scheduler"""
        if self._scheduler.running:
            logger.warning("Scheduler is already running")
            return
        
        # Schedule daily expiry check at midnight
        self._scheduler.add_job(
            func=self.check_and_deactivate_expired_ads,
            trigger=CronTrigger(hour=0, minute=0),  # Runs daily at 00:00
            id='ad_expiry_check',
            name='Check and deactivate expired ads',
            replace_existing=True,
            max_instances=1
        )
        
        # Optional: Schedule Pinecone cleanup (runs every 6 hours)
        self._scheduler.add_job(
            func=self.cleanup_inactive_ads_from_pinecone,
            trigger=CronTrigger(hour='*/6'),  # Every 6 hours
            id='pinecone_cleanup',
            name='Remove inactive ads from Pinecone',
            replace_existing=True,
            max_instances=1
        )
        
        self._scheduler.start()
        logger.info("Ad Expiry Scheduler started successfully")
    
    def stop(self):
        """Stop the scheduler"""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown()
            logger.info("Ad Expiry Scheduler stopped")
    
    def check_and_deactivate_expired_ads(self):
        """
        Main job: Check for expired ads and deactivate them
        Then remove from Pinecone
        """
        try:
            from advertisers.models import AdvertiserAd
            
            logger.info("Starting expired ads check...")
            
            today = timezone.now().date()
            
            # Find all expired ads that are still active
            expired_ads = AdvertiserAd.objects.filter(
                is_active=True,
                end_date__lt=today
            )
            
            count = expired_ads.count()
            
            if count == 0:
                logger.info("No expired ads found")
                return
            
            # Get IDs before deactivating
            expired_ad_ids = list(expired_ads.values_list('id', flat=True))
            
            # Deactivate expired ads
            updated = expired_ads.update(is_active=False, updated_at=timezone.now())
            
            logger.info(f"Deactivated {updated} expired ads: IDs {expired_ad_ids}")
            
            # Remove from Pinecone
            self._remove_ads_from_pinecone(expired_ad_ids)
            
            # Log summary
            self._log_expiry_summary(expired_ad_ids)
        
        except Exception as e:
            logger.error(f"Failed to check/deactivate expired ads: {e}", exc_info=True)
    
    def cleanup_inactive_ads_from_pinecone(self):
        """
        Cleanup job: Remove ALL inactive ads from Pinecone
        Runs periodically to ensure sync between Django DB and Pinecone
        """
        try:
            from advertisers.models import AdvertiserAd
            
            logger.info("Starting Pinecone cleanup for inactive ads...")
            
            # Get all inactive ad IDs
            inactive_ad_ids = list(
                AdvertiserAd.objects.filter(
                    is_active=False
                ).values_list('id', flat=True)
            )
            
            if not inactive_ad_ids:
                logger.info("No inactive ads to clean up from Pinecone")
                return
            
            logger.info(f"Found {len(inactive_ad_ids)} inactive ads to remove from Pinecone")
            
            # Remove from Pinecone
            self._remove_ads_from_pinecone(inactive_ad_ids)
        
        except Exception as e:
            logger.error(f"Failed to cleanup Pinecone: {e}", exc_info=True)
    
    def _remove_ads_from_pinecone(self, ad_ids: list):
        """
        Remove ads from Pinecone vector database
        
        Args:
            ad_ids: List of ad IDs to remove
        """
        if not ad_ids:
            return
        
        try:
            from user.ad_retrieval import get_retrieval_system
            
            system = get_retrieval_system()
            
            success_count = 0
            failed_count = 0
            
            for ad_id in ad_ids:
                try:
                    system.delete_ad(ad_id)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to delete ad {ad_id} from Pinecone: {e}")
                    failed_count += 1
            
            logger.info(
                f"Pinecone cleanup complete: "
                f"{success_count} deleted, {failed_count} failed"
            )
        
        except Exception as e:
            logger.error(f"Pinecone removal failed: {e}", exc_info=True)
    
    def _log_expiry_summary(self, expired_ad_ids: list):
        """Log summary of expired ads"""
        try:
            from advertisers.models import AdvertiserAd
            
            if not expired_ad_ids:
                return
            
            # Get details of expired ads
            expired_ads = AdvertiserAd.objects.filter(id__in=expired_ad_ids)
            
            summary = []
            for ad in expired_ads:
                summary.append(
                    f"- ID {ad.id}: '{ad.title}' "
                    f"(ended {ad.end_date}, advertiser: {ad.advertiser.username})"
                )
            
            logger.info(
                f"Expired ads summary:\n" + "\n".join(summary)
            )
        
        except Exception as e:
            logger.warning(f"Failed to generate expiry summary: {e}")
    
    def force_check_now(self):
        """
        Utility method: Force immediate expiry check (for testing/debugging)
        Can be called from Django shell
        """
        logger.info("Forcing immediate expiry check...")
        self.check_and_deactivate_expired_ads()
    
    def force_cleanup_now(self):
        """
        Utility method: Force immediate Pinecone cleanup (for testing/debugging)
        """
        logger.info("Forcing immediate Pinecone cleanup...")
        self.cleanup_inactive_ads_from_pinecone()
    
    def get_status(self):
        """Get scheduler status"""
        if not self._scheduler:
            return "Not initialized"
        
        if self._scheduler.running:
            jobs = self._scheduler.get_jobs()
            return {
                'status': 'running',
                'jobs': [
                    {
                        'id': job.id,
                        'name': job.name,
                        'next_run': str(job.next_run_time) if job.next_run_time else None
                    }
                    for job in jobs
                ]
            }
        
        return "Stopped"


# Global instance
_scheduler_instance = None

def get_scheduler() -> AdExpiryScheduler:
    """Get singleton scheduler instance"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = AdExpiryScheduler()
    return _scheduler_instance


def start_scheduler():
    """Start the scheduler (called from AppConfig)"""
    scheduler = get_scheduler()
    scheduler.start()


def stop_scheduler():
    """Stop the scheduler (called during shutdown)"""
    scheduler = get_scheduler()
    scheduler.stop()