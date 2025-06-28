from django.db import models
from django.utils import timezone
from datetime import timedelta

class DrawOffset(models.Model):
    offset_seconds = models.IntegerField(default=0)

    def __str__(self):
        return f"Offset: {self.offset_seconds} seconds"

    @classmethod
    def get_offset(cls):
        obj, created = cls.objects.get_or_create(id=1)
        return timedelta(seconds=obj.offset_seconds)

    @classmethod
    def add_offset(cls, minutes=0, seconds=0):
        obj, _ = cls.objects.get_or_create(id=1)
        obj.offset_seconds += (minutes * 60) + seconds
        obj.save()

    @classmethod
    def reset_offset(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        obj.offset_seconds = 0
        obj.save()

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

