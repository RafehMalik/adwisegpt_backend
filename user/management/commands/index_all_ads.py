from django.core.management.base import BaseCommand
from user.ad_retrieval import get_retrieval_system

class Command(BaseCommand):
    help = 'Index all existing ads into vectorstore'
    
    def handle(self, *args, **options):
        self.stdout.write('Starting bulk indexing...')
        
        system = get_retrieval_system()
        count = system.bulk_index_all_ads()
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully indexed {count} ads')
        )
