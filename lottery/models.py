from django.db import models
from django.utils import timezone
from datetime import timedelta

class LotteryResult(models.Model):
    date = models.DateField(auto_now_add=True)
    time_slot = models.TimeField()
    row = models.IntegerField()
    column = models.IntegerField()
    number = models.CharField(max_length=4)
    created_at = models.DateTimeField(auto_now_add=True)
    # editable_until = models.DateTimeField()
    # def is_editable(self):
    #     return timezone.now() <= self.editable_until

    @property
    def first_two_digits(self):
        return f"{self.row * 10 + self.column:02}"

    @property
    def last_two_digits(self):
        return self.number[2:]

    @property
    def is_editable(self):
        return True 

