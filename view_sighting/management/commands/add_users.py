from django.contrib.auth import get_user_model
from django.core.management import BaseCommand

import json
# import uuid


class Command(BaseCommand):
    help = 'Create users'

    def add_arguments(self, parser):
        parser.add_argument('--json_path', type=str, help='Path to JSON of users to create.')

    def handle(self, *args, **kwargs):
        User = get_user_model()
        with open(kwargs['json_path']) as json_file:
            json_data = json.load(json_file)

        for entry in json_data:
            # User.objects.get(username=entry['username']).delete()
            user = User.objects.create_user(entry['username'], entry['email'], entry['password'])
            user.expert = entry['expert']
            user.is_staff = entry['superuser']
            user.first_name = entry['first_name']
            user.last_name = entry['last_name']
            user.save()
