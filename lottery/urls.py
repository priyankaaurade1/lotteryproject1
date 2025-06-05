from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),

    path('adminpanel/', views.admin_result_panel, name='admin_panel'),
    path('adminpanel/edit/', views.edit_results, name='edit_results'),
    # path('adminpanel/update/<int:pk>/', views.update_result, name='update_result'),
    path('adminpanel/history/', views.results_history, name='results_history'),
    path('adminpanel/update/', views.update_all_results, name='update_all_results'),

]
