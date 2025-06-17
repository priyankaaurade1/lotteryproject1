from django.shortcuts import render, get_object_or_404, redirect
from .models import LotteryResult
from datetime import date, datetime, time, timedelta
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from collections import defaultdict,OrderedDict
from django.db.models import Prefetch
from django.contrib.auth import authenticate, login
from django.contrib.sessions.models import Session
from django.contrib.auth.models import User

def logout_other_superusers(current_user):
    """Log out all other superusers except the current one"""
    for session in Session.objects.all():
        data = session.get_decoded()
        user_id = data.get('_auth_user_id')

        if user_id and str(user_id) != str(current_user.id):
            try:
                other_user = User.objects.get(id=user_id)
                if other_user.is_superuser:
                    session.delete()  # force logout
            except User.DoesNotExist:
                pass

def custom_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_superuser:
                logout_other_superusers(user)

            login(request, user)
            return redirect('/adminpanel/dashboard/')
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'login.html')

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
    now = timezone.localtime()
    today = now.date()

    # Step 1: Build all time slots (15-min intervals from 9:00 AM to 9:30 PM)
    start = datetime.combine(today, time(9, 0))
    end = datetime.combine(today, time(21, 30))

    time_slots = []
    while start <= end:
        time_slots.append(start.time())
        start += timedelta(minutes=15)

    # Step 2: Find the next time slot after now
    next_slot = next((slot for slot in time_slots if slot > now.time()), None)

    if not next_slot:
        # If day is over, show message or last slot optionally
        return render(request, 'lottery/edit_results.html', {
            'table': None,
            'time_slot': None,
            'message': 'No upcoming slot available for today.'
        })

    # Step 3: Fetch results for today and next time slot
    results = LotteryResult.objects.filter(date=today, time_slot=next_slot)

    # Step 4: Fill 10x10 grid
    table = [[None for _ in range(10)] for _ in range(10)]
    for result in results:
        table[result.row][result.column] = result

    return render(request, 'lottery/edit_results.html', {
        'table': table,
        'time_slot': next_slot.strftime('%I:%M %p'),
    })

@login_required
def update_result(request, pk):
    result = get_object_or_404(LotteryResult, pk=pk)

    if request.method == 'POST' and result.is_editable:
        new_last_two = request.POST.get('last_two', '')
        if new_last_two.isdigit() and len(new_last_two) == 2:
            result.number = result.first_two_digits + new_last_two
            result.save()
    return redirect('edit_results')

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

def index(request):
    now = timezone.localtime()
    today = now.date()

    # Time slots from 9:00 AM to 9:30 PM
    time_slots = []
    start = datetime.combine(today, time(9, 0))
    end = datetime.combine(today, time(21, 30))
    while start <= end:
        time_slots.append(start.strftime('%I:%M %p'))
        start += timedelta(minutes=15)

    # --- Get Form Values ---
    selected_date = request.POST.get("date")
    selected_time = request.POST.get("time")
    show_history = request.POST.get("show_history")

    # Set show_history and history_mode depending on request type
    if request.method == "POST":
        show_history = request.POST.get("show_history") or "3"
        history_mode = request.POST.get("history_mode") or "full"
    else:
        show_history = "4"
        history_mode = "full"

    # --- Date Parsing ---
    if selected_date:
        try:
            selected_date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()
        except ValueError:
            selected_date_obj = today
    else:
        selected_date_obj = today
        selected_date = today.strftime("%Y-%m-%d")

    # --- Time Parsing ---
    selected_time_obj = None  
    if show_history == "1":
        selected_time = None  
        selected_time_obj = None
    elif selected_time:
        try:
            selected_time_obj = datetime.strptime(selected_time, "%H:%M").time()
        except ValueError:
            selected_time_obj = None
    elif selected_date_obj == today:
        selected_time_obj = get_last_time_slot(now).time()
        selected_time = selected_time_obj.strftime('%I:%M %p')


    results_exist = False
    current_slot_label = ""
    grid = [[None for _ in range(10)] for _ in range(10)]
    history_data = []
    current_time = now.time()
    if request.method == "POST":
        history_mode = request.POST.get("history_mode") or history_mode
    chart_data = []
    chart_prefix = "00"

    print(f"--- Mode: {show_history} ---")
    print(f"Selected Date: {selected_date_obj}, Time: {selected_time_obj}")
    print(f"Total results in DB: {LotteryResult.objects.filter(date=selected_date_obj).count()}")

    #  if user selected -- All Times -- from dropdown and clicked submit
    if request.method == "POST" and request.POST.get("time") == "" and request.POST.get("mode") == "full":
        show_history = "4"
        history_mode = "full"

        history_data = []

        # Fetch all results for selected date
        all_results = LotteryResult.objects.filter(date=selected_date_obj).order_by('time_slot')

        # Group results by time slot
        time_slot_groups = {}
        for result in all_results:
            time_label = result.time_slot.strftime("%I:%M %p")
            if time_label not in time_slot_groups:
                time_slot_groups[time_label] = [[None for _ in range(10)] for _ in range(10)]
            if result.row < 10 and result.column < 10:
                time_slot_groups[time_label][result.row][result.column] = result

        # Add to history_data
        for label, rows in time_slot_groups.items():
            history_data.append((label, rows))

    if  show_history == "4":
        raw_history = defaultdict(lambda: [[None for _ in range(10)] for _ in range(10)])
        if selected_date_obj == today:
            all_results = LotteryResult.objects.filter(
                date=selected_date_obj,
                time_slot__lte=current_time
            ).order_by('time_slot')
        else:
            all_results = LotteryResult.objects.filter(date=selected_date_obj).order_by('time_slot')
        results_exist = all_results.exists()

        for result in all_results:
            time_label = f"{selected_date_obj.strftime('%d-%m-%Y')} - {result.time_slot.strftime('%I:%M %p')}"
            cell_value = result

            if history_mode == "single" and len(result.number) >= 3:
                cell_value = result.number[-2]  # 2nd last digit
            elif history_mode == "two":
                cell_value = result.number[-2:]
           
            raw_history[time_label][result.row][result.column] = cell_value
            # print(f"Result: {result.number}, Row: {result.row}, Column: {result.column}, Time: {time_label}")

        # Sort by datetime descending
        history_data = sorted(raw_history.items(), key=lambda x: datetime.strptime(x[0].split(" - ")[1], "%I:%M %p"), reverse=True)
    elif show_history == "2":  # TWO
        grid = [[None for _ in range(10)] for _ in range(10)]

        if selected_time_obj:
            results = LotteryResult.objects.filter(date=selected_date_obj, time_slot=selected_time_obj)
        elif selected_date_obj == today:
            selected_time_obj = get_last_time_slot(now).time()
            selected_time = selected_time_obj.strftime('%I:%M %p')
            results = LotteryResult.objects.filter(date=today, time_slot=selected_time_obj)
        else:
            results = LotteryResult.objects.filter(date=selected_date_obj)

        results_exist = results.exists()
        current_slot_label = selected_time_obj.strftime('%I:%M %p') if selected_time_obj else ""

        for result in results:
            if result.row < 10 and result.column < 10:
                grid[result.row][result.column] = result.number[-2:]

    elif show_history == "1":  # SINGLE
        grid = [[None for _ in range(10)] for _ in range(10)]

        if selected_time_obj:
            results = LotteryResult.objects.filter(date=selected_date_obj, time_slot=selected_time_obj)
        elif selected_date_obj == today:
            selected_time_obj = get_last_time_slot(now).time()
            selected_time = selected_time_obj.strftime('%I:%M %p')
            results = LotteryResult.objects.filter(date=today, time_slot=selected_time_obj)
        else:
            results = LotteryResult.objects.filter(date=selected_date_obj)
        results_exist = results.exists()

        for result in results:
            if result.row < 10 and result.column < 10:
                if len(result.number) >= 3:
                    grid[result.row][result.column] = result.number[-2]
           
    elif show_history in [None, "", "3"]:  # FULL
        grid = [[None for _ in range(10)] for _ in range(10)]
        selected_time_obj = None
        user_selected_time = request.POST.get("time")  

        if selected_time:
            try:
                selected_time_obj = datetime.strptime(selected_time, "%I:%M %p").time()
            except ValueError:
                selected_time_obj = None

        # If form submitted with empty time, show All Times
        if not selected_time and user_selected_time == "":
            results = LotteryResult.objects.filter(date=selected_date_obj).order_by('time_slot')
            current_slot_label = "All Times"

        #  If selected_time_obj exists, show filtered time slot
        elif selected_time_obj:
            results = LotteryResult.objects.filter(date=selected_date_obj, time_slot=selected_time_obj)
            current_slot_label = selected_time

        #  If initial load and no user time selection, show latest time for today
        else:
            if selected_date_obj == today:
                selected_time_obj = get_last_time_slot(now).time()
                selected_time = selected_time_obj.strftime('%I:%M %p')
                results = LotteryResult.objects.filter(date=selected_date_obj, time_slot=selected_time_obj)
                current_slot_label = selected_time
            else:
                results = LotteryResult.objects.filter(date=selected_date_obj).order_by('time_slot')
                current_slot_label = "All Times"

        results_exist = results.exists()
        for result in results:
            if result.row < 10 and result.column < 10:
                grid[result.row][result.column] = result
    if request.method == "POST":
        history_mode = request.POST.get("history_mode")
        if history_mode == "chart":
            show_history = "4"
            chart_data = []

            chart_prefix = request.POST.get("chart_prefix") or "00"
            prefix_range_start = int(chart_prefix)
            prefix_range_end = prefix_range_start + 9
            # Current time (local)
            now = timezone.localtime()
            current_time_only = now.time()
            # Filter out results for future time slots
            all_results = LotteryResult.objects.filter(
                date=selected_date_obj,
                time_slot__lte=current_time_only
            ).order_by('-time_slot')

            for time_slot in all_results.values_list('time_slot', flat=True).distinct():
                row = ["--"] * 10
                slot_results = LotteryResult.objects.filter(
                    date=selected_date_obj,
                    time_slot=time_slot
                )

                for result in slot_results:
                    if result.number and len(result.number) >= 4:
                        number_prefix = int(result.number[:2])
                        if prefix_range_start <= number_prefix <= prefix_range_end:
                            col_index = number_prefix % 10
                            row[col_index] = result.number
                chart_data.append((time_slot.strftime("%I:%M %p"), row))

    # --- Next Draw Countdown ---
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
    print("Selected Time (raw):", selected_time)
    print("Selected Time Obj:", selected_time_obj)
    print(print("DEBUG: POSTed selected_time =", request.POST.get("debug_selected_time")))  
    print("DEBUG selected_time =", selected_time)
    print("DEBUG selected_time_obj =", selected_time_obj)
    print("DEBUG show_history =", show_history)

    column_headers = list(range(11))
    return render(request, 'index.html', {
        'grid': grid,
        'column_headers': column_headers,
        'results_exist': results_exist,
        'time_slots': time_slots,
        'selected_date': selected_date,
        'selected_time': selected_time,
        'current_slot_label': current_slot_label,
        'next_draw_str': next_draw_str,
        'next_draw_time_str': next_draw_time_str,
        'formatted_date': selected_date_obj.strftime('%d-%m-%Y'),
        'history_data': history_data,
        'show_history': show_history,
        'history_mode': history_mode,
        "chart_data": chart_data,
        "selected_chart_prefix": chart_prefix,
    })

