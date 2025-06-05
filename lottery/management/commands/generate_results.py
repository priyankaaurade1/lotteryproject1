from django.core.management.base import BaseCommand
from lottery.models import LotteryResult
from datetime import datetime, timedelta, time
import random

class Command(BaseCommand):
    help = "Auto-generate 10x10 lottery results every 15 minutes"

    def handle(self, *args, **kwargs):
        now = datetime.now()
        # Round up to the next 15-minute slot
        next_minutes = ((now.minute // 15) + 1) * 15
        next_slot_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=next_minutes)

        # Ensure the slot is between 09:00 and 21:30
        # if not time(9, 0) <= next_slot_time.time() <= time(21, 30):
        #     self.stdout.write(self.style.WARNING(f"⚠️ Skipping — {next_slot_time.strftime('%I:%M %p')} is outside allowed time slots."))
        #     return

        today = next_slot_time.date()

        for i in range(100):
            row = i // 10
            column = i % 10
            # Generate number: First 2 digits = index (00-99), Last 2 digits = random
            prefix = f"{i:02}"
            suffix = f"{random.randint(0, 99):02}"
            number = f"{prefix}{suffix}"

            LotteryResult.objects.get_or_create(
                date=today,
                time_slot=next_slot_time.time(),
                row=row,
                column=column,
                defaults={'number': number}
            )

        self.stdout.write(self.style.SUCCESS(f'✅ Generated results for slot: {next_slot_time.strftime("%I:%M %p")}'))
