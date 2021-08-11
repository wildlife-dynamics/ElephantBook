from django.conf import settings
from django.core.management import BaseCommand

import requests
import tqdm

from view_sighting.models import Group_Sighting


class Command(BaseCommand):
    help = 'Add missing EarthRanger serials'

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **kwargs):
        for group_sighting in tqdm.tqdm(Group_Sighting.objects.all()):
            endpoint = f'{settings.ER_MAIN}event/{group_sighting.earthranger_id}'

            headers = {'Authorization': f'Bearer {settings.BEARER}'}
            rsp = requests.get(endpoint, headers=headers)
            if 'data' not in rsp.json():
                print('nope')
                continue
            group_sighting.json = rsp.json()['data']
            group_sighting.save()
