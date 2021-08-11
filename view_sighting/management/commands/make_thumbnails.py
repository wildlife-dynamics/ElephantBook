from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.management import BaseCommand

from io import BytesIO
from itertools import chain
import os
import pandas as pd
from PIL import Image
import sys
import tqdm

from view_sighting.models import Sighting_Photo, Individual_Photo
from view_sighting.views import EXIF_ORIENTATION

MAXW = 100
JPEG_QUALITY = 50


class Command(BaseCommand):
    help = 'Add thumbnails to photos.'

    def handle(self, *args, **kwargs):
        media_dir = os.path.join(settings.BASE_DIR, 'media')

        for photo in tqdm.tqdm(Sighting_Photo.objects.all(), desc='Sighting Photos'):
            im = Image.open(f'media/{photo.image.name}')
            if im._exif is not None and 274 in im._exif and im._exif[274] in EXIF_ORIENTATION:
                im = im.rotate(EXIF_ORIENTATION[im._exif[274]], expand=True)

            im.thumbnail([MAXW, MAXW])

            b = BytesIO()
            im.save(b, format='JPEG', quality=JPEG_QUALITY)
            b.seek(0)

            photo.thumbnail = InMemoryUploadedFile(b, 'ImageField',
                                                   'thumbnail_%s.jpg' % photo.image.name.split('.')[0].split('/')[1],
                                                   'image/jpeg', sys.getsizeof(b), None)
            photo.thumbnail.field.upload_to = f'earthranger/{photo.group_sighting.earthranger_id}'

            new_path = os.path.join(media_dir, str(photo.thumbnail.field.upload_to), photo.thumbnail.name)
            if os.path.exists(new_path):
                os.remove(new_path)
            photo.save()

        # for photo in tqdm.tqdm(Individual_Photo.objects.all(), desc='Individual Photos'):
        #     im = Image.open(f'media/{photo.image.name}')
        #     if im._exif is not None and 274 in im._exif and im._exif[274] in EXIF_ORIENTATION:
        #         im = im.rotate(EXIF_ORIENTATION[im._exif[274]], expand=True)

        #     im.thumbnail([MAXW, MAXW])

        #     b = BytesIO()
        #     im.save(b, format='JPEG', quality=JPEG_QUALITY)
        #     b.seek(0)

        #     photo.thumbnail = InMemoryUploadedFile(b, 'ImageField', 'thumbnail_%s.jpg' % photo.image.name.split('.')[
        #                                            0].split('/')[1], 'image/jpeg', sys.getsizeof(b), None)
        #     photo.thumbnail.field.upload_to = f'individual/{photo.individual.id}'

        #     new_path = os.path.join(media_dir, str(photo.thumbnail.field.upload_to), photo.thumbnail.name)
        #     if os.path.exists(new_path):
        #         os.remove(new_path)
        #     photo.save()
