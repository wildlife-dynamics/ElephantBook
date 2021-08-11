from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.management import BaseCommand

from io import BytesIO
import os
import pandas as pd
from PIL import Image
import tqdm

from view_sighting.models import Sighting_Photo, Bounding_Box
from view_sighting.views import EXIF_ORIENTATION

import matplotlib.pyplot as plt


class Command(BaseCommand):
    help = 'Fix rotation of photos.'

    def handle(self, *args, **kwargs):
        for sighting_photo in Sighting_Photo.objects.all():
            im = Image.open(f'media/{sighting_photo.image.name}')

            if im._exif is not None and 274 in im._exif and im._exif[274] in [3, 6, 8]:
                compressed_im = Image.open(f'media/{sighting_photo.compressed_image.name}')
                if abs(compressed_im.size[0] / compressed_im.size[1] - im.size[0] / im.size[1]) < 0.05:
                    image_io = BytesIO()
                    compressed_im = compressed_im.rotate(EXIF_ORIENTATION[im._exif[274]], expand=True)
                    compressed_im.save(image_io, format='JPEG')

                    assert os.path.exists(f'media/{sighting_photo.compressed_image.name}')
                    os.remove(f'media/{sighting_photo.compressed_image.name}')
                    assert not os.path.exists(f'media/{sighting_photo.compressed_image.name}')

                    sighting_photo.compressed_image = InMemoryUploadedFile(
                        image_io, None, os.path.basename(sighting_photo.compressed_image.name), 'image/jpeg',
                        image_io.getbuffer().nbytes, None)

                    sighting_photo.compressed_image.field.upload_to = os.path.dirname(sighting_photo.image.name)
                    sighting_photo.save()

                    for bbox in sighting_photo.sighting_bounding_box_set.all():
                        for _ in range(EXIF_ORIENTATION[im._exif[274]] // 90):
                            bbox.x, bbox.y = bbox.y, 1 - bbox.x - bbox.w
                            bbox.h, bbox.w = bbox.w, bbox.h
                        bbox.save()
