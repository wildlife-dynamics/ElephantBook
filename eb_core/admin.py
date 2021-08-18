from django.contrib import admin

from .models import *

import django.db.models.fields
from django.http import HttpResponse
import json
import numpy as np
import pandas as pd


class Seek_Identity_Admin(admin.ModelAdmin):
    def export(self, request, queryset):
        entries = [{
            'author': query.author.username,
            'individual': query.individual.name,
            'code': str(query),
        } for query in queryset]
        response = HttpResponse(json.dumps(entries, indent=2), content_type='application/json')
        response['Content-Disposition'] = 'attachment; filename="seek.json"'
        return response

    actions = [export]
    search_fields = ['=author__username', '=individual__name']


class Individual_Admin(admin.ModelAdmin):
    def co_occurrence(self, request, queryset):
        queryset = queryset.order_by('id')
        pks = np.array([individual.pk for individual in queryset])
        pk_map = dict(zip(pks, range(len(pks))))

        weights = np.zeros(shape=(len(pks), len(pks)), dtype=np.uint16)

        for individual in queryset:
            for individual_sighting_1 in individual.individual_sighting_set.all():
                for individual_sighting_2 in individual_sighting_1.group_sighting.individual_sighting_set.all():
                    if individual_sighting_2.individual is not None:
                        weights[pk_map[individual.pk]][pk_map[individual_sighting_2.individual.pk]] += 1

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="co-occurrence.csv"'

        pd.DataFrame(data=weights, columns=pks, index=pks).to_csv(response)

        return response

    def export(self, request, queryset):
        queryset = queryset.order_by('id')
        seek_fields = [
            field for field in Seek_Identity._meta.get_fields() if type(field) == django.db.models.fields.CharField
        ]

        data = []
        for individual in queryset:
            entry = {
                'name': individual.name,
                'num_sightings': individual.individual_sighting_set.count(),
            }
            entry['sighting_times'] = [
                str(individual_sighting.group_sighting.datetime)
                for individual_sighting in individual.individual_sighting_set.order_by('group_sighting__datetime')
            ]
            if entry['num_sightings']:
                seek_code = individual.individual_sighting_set.latest().seek_identity
                entry.update({field.name: getattr(seek_code, field.name) for field in seek_fields})
            data.append(entry)
        df = pd.DataFrame(data)
        df.index = [individual.pk for individual in queryset]

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="individuals.csv"'

        df.to_csv(response)

        return response

    actions = [co_occurrence, export]
    search_fields = ['=name']


admin.site.register(Individual_Sighting)
admin.site.register(Group_Sighting)
admin.site.register(Social_Sighting)
admin.site.register(Individual, Individual_Admin)
admin.site.register(Seek_Identity, Seek_Identity_Admin)

admin.site.register(Sighting_Photo)
admin.site.register(Individual_Photo)

admin.site.register(Sighting_Bounding_Box)
admin.site.register(Individual_Bounding_Box)

admin.site.register(Injury)

admin.site.register(EBUser)
