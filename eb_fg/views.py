from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import authentication, permissions

from eb_core.models import *
from django.conf import settings


class Dump_View(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, format=None):
        dump = [{
            'name':
            individual.name,
            'id':
            individual.id,
            'seek':
            str(individual.individual_sighting_set.latest().seek_identity),
            'pfp':
            '' if individual.profile is None else individual.profile.compressed_image.url,
            'sightings': [{
                'datetime': individual_sighting.group_sighting.datetime.isoformat(),
                'lat': individual_sighting.group_sighting.lat,
                'lon': individual_sighting.group_sighting.lon,
            } for individual_sighting in individual.individual_sighting_set.all()]
        } for individual in Individual.objects.all() if individual.individual_sighting_set.exists()]

        return Response(dump)


class Info_View(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, format=None):
        info = {
            'tiles': r'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            'timezone': settings.TIME_ZONE,
        }

        return Response(info)
