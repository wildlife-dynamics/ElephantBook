from django.core.management import BaseCommand

import numpy as np
import pandas as pd

from view_sighting.models import Individual


class Command(BaseCommand):
    help = 'Export co-occurrence matrix'

    def add_arguments(self, parser):
        parser.add_argument('--out', type=str, default='out.csv')

    def handle(self, *args, **kwargs):
        individuals = Individual.objects.all()
        pks = np.array([individual.pk for individual in individuals])
        pk_map = dict(zip(pks, range(len(pks))))

        weights = np.zeros(shape=(len(pks), len(pks)), dtype=np.uint16)

        for individual in individuals:
            for individual_sighting_1 in individual.individual_sighting_set.all():
                for individual_sighting_2 in individual_sighting_1.group_sighting.individual_sighting_set.all():
                    if individual_sighting_2.individual is not None:
                        weights[pk_map[individual.pk]][pk_map[individual_sighting_2.individual.pk]] += 1

        pd.DataFrame(data=weights, columns=pks, index=pks).to_csv(kwargs['out'])
