from django.db.models.signals import post_save, post_delete,pre_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta

from .models import AdvertiserAd
from .models import UserSubscription,SubscriptionPayment
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=AdvertiserAd)
def sync_ad_on_save(sender, instance, created, **kwargs):
    """Auto-sync ad to vectorstore when created/updated"""
    try:
        from user.ad_retrieval import get_retrieval_system
        
        system = get_retrieval_system()
        
        ad_data = {
            'title': instance.title,
            'description': instance.description,
            'category': instance.category,
            'target_keywords': instance.target_keywords
        }
        
        system.add_or_update_ad(instance.id, ad_data)
        
        action = "Created" if created else "Updated"
        logger.info(f"{action} ad {instance.id} in vectorstore")
    
    except Exception as e:
        logger.error(f"Failed to sync ad {instance.id}: {e}")


@receiver(post_delete, sender=AdvertiserAd)
def sync_ad_on_delete(sender, instance, **kwargs):
    """Auto-delete ad from vectorstore"""
    try:
        from user.ad_retrieval import get_retrieval_system
        
        system = get_retrieval_system()
        system.delete_ad(instance.id)
        
        logger.info(f"Deleted ad {instance.id} from vectorstore")
    
    except Exception as e:
        logger.error(f"Failed to delete ad {instance.id}: {e}")



@receiver(post_save, sender=SubscriptionPayment)
def activate_subscription_on_approval(sender, instance, created, **kwargs):
    # We only care if the status was just changed to 'approved'
    # For a real project, you'd check if status changed from 'pending' -> 'approved'
    if instance.status == "approved":
        # 1. Deactivate any currently active subscription for this user
        UserSubscription.objects.filter(user=instance.user, is_active=True).update(is_active=False)

        # 2. Update or Create the subscription
        # This handles both new users and renewals
        UserSubscription.objects.update_or_create(
            user=instance.user,
            defaults={
                'plan': instance.plan,
                'is_active': True,
                'expires_at': timezone.now() + timedelta(days=30),
                'remaining_impressions': instance.plan.impression_limit,
                'used_impressions': 0,
            }
        )