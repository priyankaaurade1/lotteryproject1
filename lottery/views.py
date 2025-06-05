from django.shortcuts import render, get_object_or_404, redirect
from .models import LotteryResult
from datetime import date
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth.decorators import login_required

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
    
    # Create grid
    table = [[None for _ in range(10)] for _ in range(10)]
    for result in recent_results:
        table[result.row][result.column] = result

    return render(request, 'lottery/edit_results.html', {
        'table': table,
        'now': now,
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
def results_history(request):
    all_results = LotteryResult.objects.order_by('-date', '-time_slot')
    return render(request, 'lottery/results_history.html', {'results': all_results})
