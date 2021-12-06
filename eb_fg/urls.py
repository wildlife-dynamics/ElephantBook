from django.urls import path
from . import views

urlpatterns = [
    path('dump/', views.Dump_View.as_view()),
    path('info/', views.Info_View.as_view()),
]