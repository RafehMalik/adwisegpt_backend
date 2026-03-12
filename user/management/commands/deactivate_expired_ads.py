# File: advertiser/management/commands/deactivate_expired_ads.py
"""
Management command to deactivate expired ads.
Run this as a cron job daily or use Celery beat for scheduled execution.

Usage:
    python manage.py deactivate_expired_ads
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from advertisers.models import AdvertiserAd


class Command(BaseCommand):
    help = 'Deactivate ads that have expired (end_date has passed)'

    def handle(self, *args, **options):
        today = timezone.now().date()
        
        # Find all active ads that have expired
        expired_ads = AdvertiserAd.objects.filter(
            is_active=True,
            end_date__lt=today
        )
        
        count = expired_ads.count()
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS('No expired ads found.')
            )
            return
        
        # Deactivate them
        expired_ads.update(is_active=False)
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully deactivated {count} expired ad(s).'
            )
        )
        
        # Log details
        for ad in expired_ads:
            self.stdout.write(
                f'  - Deactivated: {ad.title} (ID: {ad.id}, End Date: {ad.end_date})'
            )