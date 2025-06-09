from django.shortcuts import render, get_object_or_404, redirect
from .models import LotteryResult
from datetime import date, datetime, time, timedelta
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from collections import defaultdict
from django.db.models import Prefetch

@login_required
def admin_result_panel(request):
    today = date.today()
    results = LotteryResult.objects.filter(date=today).order_by('row', 'column')
    table = [[None for _ in range(10)] for _ in range(10)]

    for result in results:
        table[result.row][result.column] = result

    return render(request, 'lottery/admin_panel.html', {'table': table})

@login_required
def edit_results(request):
    today = date.today()
    now = timezone.now()
    recent_results = LotteryResult.objects.filter(date=today).order_by('row', 'column')

    table = [[None for _ in range(10)] for _ in range(10)]
    for result in recent_results:
        # Log or print this to confirm
        print(f"{result.row},{result.column} - Editable? {result.is_editable}")
        table[result.row][result.column] = result

    return render(request, 'lottery/edit_results.html', {
        'table': table,
        'now': now,
    })

# @login_required
# def update_result(request, pk):
#     result = get_object_or_404(LotteryResult, pk=pk)

#     if request.method == 'POST' and result.is_editable:
#         new_last_two = request.POST.get('last_two', '')
#         if new_last_two.isdigit() and len(new_last_two) == 2:
#             result.number = result.first_two_digits + new_last_two
#             result.save()
#     return redirect('edit_results')

@login_required
def update_all_results(request):
    if request.method == 'POST':
        ids = request.POST.getlist('ids')

        for pk in ids:
            result = get_object_or_404(LotteryResult, pk=pk)
            if result.is_editable:
                key = f'last_two_{pk}'
                new_last_two = request.POST.get(key, '')
                if new_last_two.isdigit() and len(new_last_two) == 2:
                    result.number = result.first_two_digits + new_last_two
                    result.save()
    messages.success(request, "Lottery results updated successfully!")
    return redirect('edit_results')

@login_required
def results_history(request):
    all_results = LotteryResult.objects.order_by('-date', '-time_slot')

    # Group by (date, time_slot)
    grouped = defaultdict(list)
    for result in all_results:
        key = (result.date, result.time_slot)
        grouped[key].append(result)

    # Convert each group into a 10x10 table (matrix)
    result_tables = []
    for (date, time_slot), results in grouped.items():
        table = [[None for _ in range(10)] for _ in range(10)]
        for result in results:
            table[result.row][result.column] = result
        result_tables.append({
            'date': date,
            'time_slot': time_slot,
            'table': table
        })

    return render(request, 'lottery/results_history.html', {'result_tables': result_tables})

def get_last_time_slot(now):
    minutes = (now.minute // 15) * 15
    return now.replace(minute=minutes, second=0, microsecond=0)

def get_next_draw_time(now):
    draw_start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    draw_end = now.replace(hour=21, minute=30, second=0, microsecond=0)

    if now < draw_start:
        # Before 9:00 AM → next draw is today at 9:00 AM
        return draw_start
    elif now > draw_end:
        # After 9:30 PM → next draw is tomorrow at 9:00 AM
        next_day = now + timedelta(days=1)
        return next_day.replace(hour=9, minute=0, second=0, microsecond=0)
    else:
        # During draw period → next slot rounded to next 15-minute interval
        minutes = (now.minute // 15 + 1) * 15
        next_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minutes)
        return next_time if next_time <= draw_end else (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)

from collections import defaultdict
def index(request):
    now = timezone.localtime()
    today = now.date()

    # Time slots from 9:00 AM to 9:30 PM
    time_slots = []
    start = datetime.combine(today, time(9, 0))
    end = datetime.combine(today, time(21, 30))
    while start <= end:
        time_slots.append(start.strftime('%H:%M'))
        start += timedelta(minutes=15)

    # Get POST values
    selected_date = request.POST.get("date")
    selected_time = request.POST.get("time")

    # Parse selected date
    if selected_date:
        try:
            selected_date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()
        except ValueError:
            selected_date_obj = today
    else:
        selected_date_obj = today
        selected_date = today.strftime("%Y-%m-%d")

    # Parse selected time
    if selected_time:
        try:
            selected_time_obj = datetime.strptime(selected_time, "%H:%M").time()
        except ValueError:
            selected_time_obj = get_last_time_slot(now).time()
    else:
        selected_time_obj = None  # For history view when "-- All Times --" is selected

    results_exist = False
    current_slot_label = ""
    grid = [[None for _ in range(10)] for _ in range(10)]
    history_data = {}

    if selected_time_obj:
        # Show a specific time slot (SINGLE result)
        results = LotteryResult.objects.filter(date=selected_date_obj, time_slot=selected_time_obj)
        results_exist = results.exists()
        for result in results:
            grid[result.row][result.column] = result
        current_slot_label = selected_time_obj.strftime('%I:%M %p')
    else:
        # Show all time slots for selected date (HISTORY)
        all_results = LotteryResult.objects.filter(date=selected_date_obj).order_by('time_slot')
        results_exist = all_results.exists()
        for result in all_results:
            time_label = result.time_slot.strftime('%I:%M %p')
            if time_label not in history_data:
                history_data[time_label] = [[None for _ in range(10)] for _ in range(10)]
            history_data[time_label][result.row][result.column] = result
        current_slot_label = "All Results"

    # Next draw countdown logic
    next_draw_time = get_next_draw_time(now)
    if next_draw_time:
        time_diff = next_draw_time - now
        total_seconds = int(time_diff.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        next_draw_str = f"{hours:02}:{minutes:02}:{seconds:02}"
        next_draw_time_str = next_draw_time.strftime("%Y-%m-%dT%H:%M:%S")
    else:
        next_draw_str = "No more draws today"
        next_draw_time_str = ""

    return render(request, 'index.html', {
        'grid': grid,
        'results_exist': results_exist,
        'time_slots': time_slots,
        'selected_date': selected_date,
        'selected_time': selected_time,
        'current_slot_label': current_slot_label,
        'next_draw_str': next_draw_str,
        'next_draw_time_str': next_draw_time_str,
        'formatted_date': selected_date_obj.strftime('%d-%m-%Y'),
        'history_data': history_data,
    })