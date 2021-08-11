from django.core.files.temp import NamedTemporaryFile
from django.core.management import BaseCommand, call_command

import numpy as np
import json


class Command(BaseCommand):
    help = 'Export DB'

    def add_arguments(self, parser):
        parser.add_argument('--verbose', dest='verbose', action='store_true')
        parser.set_defaults(verbose=False)

    def handle(self, *args, **kwargs):
        tmp = NamedTemporaryFile(mode='w')

        with open(tmp.name, 'w') as f:
            call_command('dumpdata', stdout=f)

        with open(tmp.name) as f:
            data = json.load(f)

        if kwargs['verbose']:
            print('Contains')
            print(np.column_stack(np.unique([entry['model'] for entry in data], return_counts=True)))
        data = [entry for entry in data if 'view_sighting' in entry['model']]
        if kwargs['verbose']:
            print('Exporting')
            print(np.column_stack(np.unique([entry['model'] for entry in data], return_counts=True)))

        with open('dump.json', 'w') as f:
            json.dump(data, f, indent=2)
