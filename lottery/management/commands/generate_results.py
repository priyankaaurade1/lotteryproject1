from django.core.management.base import BaseCommand
from lottery.models import LotteryResult
from datetime import datetime, timedelta
import random

class Command(BaseCommand):
    help = "Auto-generate 10x10 lottery results every 15 minutes"

    def handle(self, *args, **kwargs):
        now = datetime.now()
        time_slot = now.replace(second=0, microsecond=0).time()
        today = now.date()

        for i in range(100):
            row = i // 10
            column = i % 10
            number = f"{random.randint(0, 9999):04}"
            editable_until = now + timedelta(minutes=15)

            LotteryResult.objects.get_or_create(
                date=today,
                time_slot=time_slot,
                row=row,
                column=column,
                defaults={
                    'number': number,
                    # 'editable_until': editable_until
                }
            )

        self.stdout.write(self.style.SUCCESS('✅ Generated 100 lottery results.'))
