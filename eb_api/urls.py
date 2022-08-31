from django.urls import path

from . import views

urlpatterns = [
    path("earthranger_sighting/", views.EarthRangerSightingView.as_view()),
    path("individual_sighting/", views.IndividualSightingView.as_view()),
    path("individual/", views.IndividualView.as_view()),
    path("seek_identity/", views.SeekIdentityView.as_view()),
]
