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
from django.utils.timezone import localtime,make_aware
from collections import defaultdict, namedtuple
import random
from .models import DrawOffset
from django.http import JsonResponse
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm

def get_user_sessions(user):
    now = timezone.now()
    sessions = Session.objects.all()
    user_sessions = []

    for session in sessions:
        if session.expire_date < now:
            session.delete()
            continue

        data = session.get_decoded()
        if str(data.get('_auth_user_id')) == str(user.id):
            user_sessions.append(session)
    
    return user_sessions

@login_required
def profile(request):
    user = request.user

    if request.method == 'POST':
        new_username = request.POST.get('username')
        if new_username and new_username != user.username:
            user.username = new_username
            user.save()
            messages.success(request, 'Username updated successfully!')

        password_form = PasswordChangeForm(user, request.POST)

        if password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)  # Critical: keeps user logged in after password change
            messages.success(request, 'Password changed successfully!')
            return redirect('profile')  # Redirect to clear POST data
        else:
            if request.POST.get('old_password') or request.POST.get('new_password1') or request.POST.get('new_password2'):
                # Only show errors if they tried to change password
                for field, errors in password_form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")

    else:
        password_form = PasswordChangeForm(user)

    return render(request, 'lottery/profile.html', {
        'user': user,
        'password_form': password_form
    })

def custom_login(request):
    if request.method == 'POST':
        username = request.POST.get("username")
        password = request.POST.get("password")
        force_logout = request.POST.get("force_logout")  # Flag for forced logout
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_superuser:
                existing_sessions = get_user_sessions(user)
                if existing_sessions and not force_logout:
                    # Already logged in elsewhere, show confirmation page
                    return render(request, 'confirm_force_logout.html', {
                        'username': username,
                        'password': password
                    })
                # Force logout other sessions if confirmed
                for session in existing_sessions:
                    session.delete()
            # Proceed to login
            login(request, user)
            return redirect('/adminpanel')
        else:
            messages.error(request, "Invalid username or password.")
    return render(request, 'login.html')

@login_required
def edit_results(request):
    offset = DrawOffset.get_offset()
    now = localtime()
    today = now.date()
    current_time = now.time()
    formatted_date = today.strftime('%d-%m-%Y')
    current_time_str = now.strftime('%I:%M %p')
    # ✅ Handle Reset Offset
    if request.method == "POST" and request.POST.get("reset_offset") == "1" and request.user.is_superuser:
        DrawOffset.reset_offset()
        instance = DrawOffset.objects.get(pk=1)
        instance.scheduled_draw_time = None
        instance.save()
    # ✅ Handle Add Offset (Postpone)
    if request.method == "POST" and request.POST.get("postpone") == "1" and request.user.is_superuser:
        delay_min = int(request.POST.get("delay_minutes") or 0)
        delay_sec = int(request.POST.get("delay_seconds") or 0)
        offset_delta = timedelta(minutes=delay_min, seconds=delay_sec)
        # Get current scheduled time (if any)
        scheduled = DrawOffset.get_scheduled_draw()
        if not scheduled or scheduled < now:
            scheduled = get_next_draw_time(now)
        new_scheduled = scheduled + offset_delta
        DrawOffset.set_scheduled_draw(new_scheduled)
        messages.success(request, f"Draw postponed to {new_scheduled.strftime('%I:%M %p')}.")
    # Generate time slots (static schedule)
    offset = DrawOffset.get_offset()
    start = datetime.combine(today, time(9, 0)) + offset
    end = datetime.combine(today, time(21, 30)) + offset
    time_slots = []
    while start <= end:
        time_obj = start.time()
        time_str = start.strftime("%I:%M %p")
        time_slots.append((time_str, time_obj))
        start += timedelta(minutes=15)
    # Handle selected date/time from form
    selected_date_str = request.POST.get('date')
    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date() if selected_date_str else today

    selected_slot_str = request.POST.get('time_slot')
    selected_slot = None
    for label, t in time_slots:
        if label == selected_slot_str:
            selected_slot = t
            break
    # Filter future slots with offset applied
    now_with_offset = localtime() + offset
    future_slots = [
        (label, t) for label, t in time_slots
        if selected_date > today or (selected_date == today and make_aware(datetime.combine(selected_date, t)) + offset > now_with_offset)
    ]
    # Auto-select next slot if none chosen
    if not selected_slot and future_slots:
        selected_slot_str, selected_slot = future_slots[0]
    # Nothing to edit if no slot
    if not selected_slot:
        total_seconds = 0
        return render(request, 'lottery/edit_results.html', {
            'table': None,
            'time_slot': None,
            'formatted_date': formatted_date,
            'next_draw_time_str': '',
            'next_draw_str': '',
            'current_time_str': current_time_str,
            'message': 'No upcoming slot available for today.',
            'selected_date': selected_date.strftime('%Y-%m-%d'),
            'selected_slot': None,
            'all_slots': [label for label, _ in time_slots],
            'is_editable': False,
            'total_seconds': total_seconds,
        })
    # Determine if slot is editable (cutoff 10 seconds before)
    selected_datetime = make_aware(datetime.combine(selected_date, selected_slot)) + offset
    now_with_offset = localtime() + offset
    is_editable = selected_datetime > now_with_offset + timedelta(seconds=10)
    # If selected time already over (even with offset), show tomorrow 9 AM
    if selected_datetime <= now:
        selected_datetime = make_aware(datetime.combine(today + timedelta(days=1), time(9, 0))) + offset
    next_draw_time_str = selected_datetime.strftime('%Y-%m-%dT%H:%M:%S')
    time_diff = selected_datetime - now
    total_seconds = max(0, int(time_diff.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    next_draw_str = f"{hours:02}:{minutes:02}:{seconds:02}"
    # Load or generate results table
    results = LotteryResult.objects.filter(date=selected_date, time_slot=selected_slot)
    has_real_results = results.exists()
    table = [[None for _ in range(10)] for _ in range(10)]
    if results.exists():
        for result in results:
            table[result.row][result.column] = result
    else:
        if selected_date < today:
            from collections import namedtuple
            import random
            DummyResult = namedtuple('DummyResult', ['first_two_digits', 'last_two_digits', 'pk', 'is_editable'])
            for i in range(100):
                table[i // 10][i % 10] = DummyResult(f"{i:02}", f"{random.randint(0, 99):02}", 0, False)
    return render(request, 'lottery/edit_results.html', {
        'table': table,
        'time_slot': selected_slot_str,
        'formatted_date': formatted_date,
        'next_draw_time_str': next_draw_time_str,
        'next_draw_str': next_draw_str,
        'current_time_str': current_time_str,
        'selected_date': selected_date.strftime('%Y-%m-%d'),
        'selected_slot': selected_slot_str,
        'all_slots': [label for label, _ in time_slots],
        'is_editable': is_editable and has_real_results,
        'total_seconds': total_seconds,
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
    now = localtime()
    today = now.date()
    next_draw_time_str = ""

    # --- Get selected date and time from POST
    selected_date = request.POST.get("date") or today.strftime('%Y-%m-%d')
    try:
        selected_date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()
    except ValueError:
        selected_date_obj = today

    selected_time = request.POST.get("time")  # Can be None or "All Times"
    selected_time_obj = None
    if selected_time and selected_time != "All Times":
        try:
            selected_time_obj = datetime.strptime(selected_time, "%I:%M %p").time()
        except ValueError:
            selected_time_obj = None

    # --- Generate time slots
    time_slots = []
    slot_labels = []
    start = datetime.combine(today, time(9, 0))
    end = datetime.combine(today, time(21, 30))
    while start <= end:
        slot_str = start.strftime('%I:%M %p')
        time_slots.append(slot_str)
        slot_labels.append((slot_str, start.time()))
        start += timedelta(minutes=15)

    # Reverse time_slots and slot_labels to make descending order
    time_slots.reverse()
    slot_labels.reverse()

    if selected_date_obj == today:
        found = False
        for label, time_obj in slot_labels:
            slot_dt = datetime.combine(today, time_obj)
            if make_aware(slot_dt) > now:
                next_draw_time_str = slot_dt.strftime('%Y-%m-%dT%H:%M:%S')
                found = True
                break
        if not found:
            # After 9:30 PM: set next day's 9:00 AM
            next_morning = datetime.combine(today + timedelta(days=1), time(9, 0))
            next_draw_time_str = next_morning.strftime('%Y-%m-%dT%H:%M:%S')

    # --- Filter results
    if selected_time_obj:
        all_results = LotteryResult.objects.filter(date=selected_date_obj, time_slot=selected_time_obj).order_by('-time_slot')
    else:
        all_results = LotteryResult.objects.filter(date=selected_date_obj).order_by('-time_slot')

    # --- Group results
    grouped = defaultdict(list)
    for result in all_results:
        key = (result.date, result.time_slot)
        grouped[key].append(result)

    # --- Convert to table
    result_tables = []
    DummyResult = namedtuple('DummyResult', ['number'])

    if selected_time_obj:
        slot_list = [(selected_date_obj, selected_time_obj)]
    else:
        slot_list = [(selected_date_obj, t[1]) for t in slot_labels]

    for date, time_slot in slot_list:
        results = grouped.get((date, time_slot), [])

        table = [[None for _ in range(10)] for _ in range(10)]
        if results:
            for result in results:
                table[result.row][result.column] = result
        elif date < today:
            # Fill dummy if past date and no real data
            for i in range(100):
                row = i // 10
                col = i % 10
                dummy = DummyResult(number=f"{random.randint(0, 9999):04}")
                table[row][col] = dummy

        formatted_time_slot = datetime.combine(date, time_slot).strftime('%I:%M %p')
        result_tables.append({
            'date': date.strftime('%d-%m-%Y'),
            'time_slot': formatted_time_slot,
            'table': table
        })

    no_results = len(result_tables) == 0

    return render(request, 'lottery/results_history.html', {
        'result_tables': result_tables,
        'selected_date': selected_date,
        'selected_time': selected_time,
        'time_slots': time_slots,
        'no_results': no_results,
        'next_draw_time_str': next_draw_time_str,
    })

@login_required
def next_draw_time_api(request):
    now = timezone.localtime()
    offset = DrawOffset.get_offset()
    next_draw_time = get_next_draw_time(now)
    if not next_draw_time:
        return JsonResponse({
            'next_draw_time_str': '',
            'total_seconds': 0,
        })
    # Add 30 second offset for display
    next_draw_time += timedelta(seconds=30)
    # Compute remaining seconds from now
    total_seconds = max(0, int((next_draw_time + offset - now).total_seconds()))
    print("OFFSET:", offset)
    print("NEXT DRAW:", next_draw_time)
    return JsonResponse({
        'next_draw_time_str': next_draw_time.strftime("%Y-%m-%dT%H:%M:%S"),
        'total_seconds': total_seconds,
    })

# def get_last_time_slot(now):
#     from datetime import time, timedelta
#     cutoff_time = now - timedelta(seconds=30)
#     earliest_slot = time(9, 0)
#     latest_slot = time(21, 30)
#     current_time = cutoff_time.time()
#     if current_time < earliest_slot:
#         return None  # No eligible slot yet
#     elif current_time > latest_slot:
#         return cutoff_time.replace(hour=21, minute=30, second=0, microsecond=0)
#     else:
#         # Floor to nearest 15 for cutoff time
#         minutes = (cutoff_time.minute // 15) * 15
#         return cutoff_time.replace(minute=minutes, second=0, microsecond=0)

def get_last_time_slot(now):
    from datetime import time, timedelta

    earliest_slot = time(9, 0)
    latest_slot = time(21, 30)
    current_time = now.time()

    if current_time < earliest_slot:
        return None  # No eligible slot yet
    elif current_time > latest_slot:
        return now.replace(hour=21, minute=30, second=0, microsecond=0)
    else:
        # Floor to nearest 15 for current time
        minutes = (now.minute // 15) * 15
        return now.replace(minute=minutes, second=0, microsecond=0)

def get_next_draw_time(now):
    offset = DrawOffset.get_offset()
    now_with_offset = now + offset
    # First and last draw times with offset
    draw_start = now_with_offset.replace(hour=9, minute=0, second=0, microsecond=0)
    draw_end = now_with_offset.replace(hour=21, minute=30, second=0, microsecond=0)
    if now_with_offset < draw_start:
        # Before 9:00 AM → first draw
        return draw_start - offset
    if now_with_offset > draw_end:
        # After last slot → next day 9:00 AM
        next_day = now_with_offset + timedelta(days=1)
        return next_day.replace(hour=9, minute=0, second=0, microsecond=0) - offset
    # Otherwise → round up to the next 15-minute slot
    minute_block = (now_with_offset.minute // 15 + 1) * 15
    next_time = now_with_offset.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minute_block)
    if next_time > draw_end:
        # Past last slot → next day 9:00 AM
        next_time = (now_with_offset + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    return next_time - offset

def index(request):
    now = timezone.localtime()
    today = now.date()
    current_time = now.time()
    # Get the last slot if available
    last_slot_dt = get_last_time_slot(now)
    if last_slot_dt:
        current_slot_time = last_slot_dt.time().strftime('%I:%M %p')
    else:
        current_slot_time = ""
    # Build time slot list
    time_slots = []
    start = datetime.combine(today, time(9, 0))
    end = datetime.combine(today, time(21, 30))
    while start <= end:
        time_slots.append(start.strftime('%I:%M %p'))
        start += timedelta(minutes=15)
    if request.method == "GET" or not request.POST.get("date"):
        selected_date_obj = today
    else:
        try:
            selected_date_obj = datetime.strptime(request.POST.get("date"), "%Y-%m-%d").date()
        except ValueError:
            selected_date_obj = today
    if selected_date_obj == today:
        time_slots = [t for t in time_slots if datetime.strptime(t, '%I:%M %p').time() <= current_time]
    # POST data
    selected_date = request.POST.get("date")
    selected_time = request.POST.get("time")
    show_history = request.POST.get("show_history") or "3"
    history_mode = request.POST.get("history_mode") or "full"
    mode = request.POST.get("mode") or history_mode
    # Determine selected_date_obj
    if selected_date:
        try:
            selected_date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()
        except ValueError:
            selected_date_obj = today
    else:
        selected_date_obj = today
        selected_date = today.strftime("%Y-%m-%d")
    # Determine selected_time_obj
    selected_time_obj = None
    if selected_time:
        try:
            selected_time_obj = datetime.strptime(selected_time, "%I:%M %p").time()
        except ValueError:
            selected_time_obj = None
    elif selected_date_obj == today:
        if last_slot_dt:
            selected_time_obj = last_slot_dt.time()
        else:
            selected_time_obj = time(9, 0)
        selected_time = selected_time_obj.strftime('%I:%M %p')
    # Initialize
    grid = [[None for _ in range(10)] for _ in range(10)]
    history_data = []
    chart_data = []
    chart_prefix = "00"
    results_exist = False
    current_slot_label = ""
    # All Times mode
    if request.method == "POST" and request.POST.get("time") == "" and request.POST.get("mode") == "full":
        show_history = "4"
        history_mode = "full"
        all_results = LotteryResult.objects.filter(date=selected_date_obj).order_by('time_slot')
        time_slot_groups = {}
        for result in all_results:
            label = result.time_slot.strftime("%I:%M %p")
            if label not in time_slot_groups:
                time_slot_groups[label] = [[None for _ in range(10)] for _ in range(10)]
            if result.row < 10 and result.column < 10:
                time_slot_groups[label][result.row][result.column] = result
        history_data = list(time_slot_groups.items())
    # History modes
    if show_history == "4":
        raw_history = defaultdict(lambda: [[None for _ in range(10)] for _ in range(10)])
        if selected_date_obj == today:
            all_results = LotteryResult.objects.filter(date=selected_date_obj, time_slot__lte=current_time).order_by('time_slot')
        else:
            all_results = LotteryResult.objects.filter(date=selected_date_obj).order_by('time_slot')
        results_exist = all_results.exists()
        for result in all_results:
            label = result.time_slot.strftime('%I:%M %p')
            cell_value = result
            if history_mode == "single" and len(result.number) >= 3:
                cell_value = result.number[-2]
            elif history_mode == "two":
                cell_value = result.number[-2:]
            raw_history[label][result.row][result.column] = cell_value
        history_data = sorted(raw_history.items(), key=lambda x: datetime.strptime(x[0], "%I:%M %p"), reverse=True)
    elif show_history == "2":
        if selected_time_obj:
            if selected_date_obj == today and selected_time_obj > current_time:
                results = LotteryResult.objects.none()
            else:
                results = LotteryResult.objects.filter(date=selected_date_obj, time_slot=selected_time_obj)
        elif selected_date_obj == today and last_slot_dt:
            selected_time_obj = last_slot_dt.time()
            selected_time = selected_time_obj.strftime('%I:%M %p')
            results = LotteryResult.objects.filter(date=today, time_slot=selected_time_obj)
        else:
            results = LotteryResult.objects.filter(date=selected_date_obj)

        results_exist = results.exists()
        current_slot_label = selected_time_obj.strftime('%I:%M %p') if selected_time_obj else ""
        for result in results:
            if result.row < 10 and result.column < 10:
                grid[result.row][result.column] = result.number[-2:]
    elif show_history == "1":
        if selected_time_obj:
            if selected_date_obj == today and selected_time_obj > current_time:
                results = LotteryResult.objects.none()
            else:
                results = LotteryResult.objects.filter(date=selected_date_obj, time_slot=selected_time_obj)
        elif selected_date_obj == today and last_slot_dt:
            selected_time_obj = last_slot_dt.time()
            selected_time = selected_time_obj.strftime('%I:%M %p')
            results = LotteryResult.objects.filter(date=today, time_slot=selected_time_obj)
        else:
            results = LotteryResult.objects.filter(date=selected_date_obj)
        results_exist = results.exists()
        for result in results:
            if result.row < 10 and result.column < 10 and len(result.number) >= 3:
                grid[result.row][result.column] = result.number[-2]
    elif show_history in [None, "", "3"]:
        user_selected_time = request.POST.get("time")
        if selected_time:
            try:
                selected_time_obj = datetime.strptime(selected_time, "%I:%M %p").time()
            except ValueError:
                selected_time_obj = None
        if not selected_time and user_selected_time == "":
            results = LotteryResult.objects.filter(date=selected_date_obj).order_by('time_slot')
            current_slot_label = "All Times"
        elif selected_time_obj:
            if selected_date_obj == today and selected_time_obj > current_time:
                results = LotteryResult.objects.none()
            else:
                results = LotteryResult.objects.filter(date=selected_date_obj, time_slot=selected_time_obj)
            current_slot_label = selected_time
        else:
            if selected_date_obj == today and last_slot_dt:
                selected_time_obj = last_slot_dt.time()
                selected_time = selected_time_obj.strftime('%I:%M %p')
                results = LotteryResult.objects.filter(date=selected_date_obj, time_slot=selected_time_obj)
                current_slot_label = selected_time
            else:
                results = LotteryResult.objects.none()
                current_slot_label = "All Results"
        results_exist = results.exists()
        for result in results:
            if result.row < 10 and result.column < 10:
                grid[result.row][result.column] = result
    # Chart mode
    if request.method == "POST":
        history_mode = request.POST.get("history_mode") or history_mode
        if history_mode == "chart":
            show_history = "4"
            chart_data = []
            chart_prefix = request.POST.get("chart_prefix") or "00"
            prefix_start = int(chart_prefix)
            prefix_end = prefix_start + 9
            all_results = LotteryResult.objects.filter(date=selected_date_obj, time_slot__lte=current_time).order_by('-time_slot')
            for time_slot in all_results.values_list('time_slot', flat=True).distinct():
                row = ["--"] * 10
                slot_results = LotteryResult.objects.filter(date=selected_date_obj, time_slot=time_slot)
                for result in slot_results:
                    if result.number and len(result.number) >= 4:
                        prefix = int(result.number[:2])
                        if prefix_start <= prefix <= prefix_end:
                            col_index = prefix % 10
                            row[col_index] = result.number
                chart_data.append((time_slot.strftime("%I:%M %p"), row))
    next_draw_time = get_next_draw_time(now)
    if next_draw_time:
        next_draw_time_str = next_draw_time.strftime("%Y-%m-%dT%H:%M:%S")
        auto_refresh_time_str = next_draw_time.strftime("%Y-%m-%dT%H:%M:%S")
        time_diff = now - next_draw_time
        total_seconds = abs(int(time_diff.total_seconds()))
        hours, rem = divmod(total_seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        next_draw_str = f"{hours:02}:{minutes:02}:{seconds:02}"
    else:
        next_draw_time_str = ""
        auto_refresh_time_str = ""
        next_draw_str = "No more draws today"
    column_headers = list(range(11))
    row_headers = [f"{i:02}" for i in range(0, 100, 10)]
    selected_date_display = selected_date_obj.strftime('%d-%m-%Y')
    if selected_time:
        selected_time_display = selected_time
    elif show_history == "4":
        selected_time_display = "All Times"
    elif selected_date_obj == today:
        selected_time_display = current_slot_time
    elif selected_time_obj:
        selected_time_display = selected_time_obj.strftime('%I:%M %p')
    else:
        selected_time_display = "All Times"
    has_results = any(any(cell and str(cell).strip() for cell in row) for row in grid)
    return render(request, 'index.html', {
        'grid': grid,
        'column_headers': column_headers,
        'row_headers': row_headers,
        'results_exist': results_exist,
        'time_slots': time_slots,
        'selected_date': selected_date,
        'selected_time': selected_time,
        'current_slot_label': current_slot_label,
        'next_draw_str': next_draw_str,
        'next_draw_time_str': next_draw_time_str,
        'formatted_date': selected_date_display,
        'history_data': history_data,
        'show_history': show_history,
        'history_mode': history_mode,
        'chart_data': chart_data,
        'selected_chart_prefix': chart_prefix,
        'current_slot_time': current_slot_time,
        'selected_date_display': selected_date_display,
        'selected_time_display': selected_time_display,
        'mode': mode,
        'has_results': has_results,
        'auto_refresh_time_str': auto_refresh_time_str,
        'current_time': current_time.strftime('%H:%M:%S'),
    })