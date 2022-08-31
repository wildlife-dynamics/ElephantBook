from django.urls import path

from . import views

app_name = "eb_anno"

urlpatterns = [
    path("assignment/", views.Assignment_List.as_view(), name="assignment list"),
    path("assignment/get/", views.Assignment_Get.as_view(), name="assignment get"),
    path("assignment/queue/", views.Assignment_Queue.as_view(), name="assignment queue"),
    path("assignment/completed/", views.Assignment_Completed_List.as_view(), name="assignment completed list"),
    path("assignment/needs_review/", views.Assignment_Needs_Review_List.as_view(), name="assignment needs review list"),
    path("assignment/<int:pk>/", views.Assignment_View.as_view(), name="assignment view"),
]
