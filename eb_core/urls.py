from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),

    path('add_earthranger/', views.add_earthranger, name='add earthranger'),

    path('group_sighting/', views.group_sighting_list, name='group sighting list'),
    path('group_sighting/<int:earthranger_serial>/', views.group_sighting_view, name='group sighting view'),
    path('group_sighting/<int:earthranger_serial>/edit', views.group_sighting_edit, name='group sighting edit'),

    path('social_sighting/', views.social_sighting_list, name='social sighting list'),
    path('social_sighting/<int:social_sighting_id>/', views.social_sighting_view, name='social sighting view'),
    path('social_sighting/<int:social_sighting_id>/edit', views.social_sighting_edit, name='social sighting edit'),

    path('individual_sighting/', views.individual_sighting_list, name='individual sighting list'),
    path('individual_sighting/individual/<int:individual_id>/',
         views.individual_sighting_list, name='individual sighting list individual'),
    path('individual_sighting/queue/', views.individual_sighting_queue, name='individual sighting queue'),
    path('individual_sighting/expert_queue/', views.individual_sighting_expert_queue, name='individual sighting expert queue'),
    path('individual_sighting/unidentified/', views.individual_sighting_unidentified, name='individual sighting unidentified'),
    path('individual_sighting/<int:individual_sighting_id>/',
         views.individual_sighting_view, name='individual sighting view'),
    path('individual_sighting/<int:individual_sighting_id>/edit',
         views.individual_sighting_edit, name='individual sighting edit'),

    path('individual/', views.individual_list, name='individual list'),
    path('individual/add', views.individual_add, name='individual add'),
    path('individual/combine', views.individual_combine, name='individual combine'),
    path('individual/<int:individual_id>/', views.individual_view, name='individual view'),
    path('individual/<int:individual_id>/edit', views.individual_edit, name='individual edit'),

    path('search/', views.search, name='search'),

    path('stats/', views.stats, name='stats'),

    path('view_media/<path:name>/', views.view_media, name='view media')
]
