from django.core.management import BaseCommand

from view_sighting.models import Seek_Identity


class Command(BaseCommand):
    help = 'Fix SEEK'

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **kwargs):
        for code in Seek_Identity.objects.all():
            if code.age is not None:
                code.age = code.age[0]

            print(code.age)
            code.save()
