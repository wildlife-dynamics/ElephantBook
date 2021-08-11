from django.conf import settings
from django.core.management import BaseCommand

from io import BytesIO
import os
import pandas as pd
from PIL import Image
from shutil import copyfile, move
import tqdm

from view_sighting.models import Individual_Photo, Sighting_Photo


class Command(BaseCommand):
    help = 'Fix rotation of photos.'

    def handle(self, *args, **kwargs):
        media_dir = os.path.join(settings.BASE_DIR, 'media')

        for photo in tqdm.tqdm(Sighting_Photo.objects.all()):
            #     photo.delete()
            #     continue

            # for photo in tqdm.tqdm(Individual_Photo.objects.all()):
            #     photo.delete()
            #     continue

            old_dir = os.path.split(photo.image.path)[0]
            if 'earthranger' in old_dir:
                continue

            if not photo.group_sighting.earthranger_serial:
                print('nope', photo.group_sighting.id)
                continue

            for image in (photo.image, photo.compressed_image, photo.thumbnail):
                old_file_path = os.path.join(media_dir, image.name)
                new_name = f'earthranger/{photo.group_sighting.earthranger_serial}/{os.path.basename(image.name)}'
                new_file_path = os.path.join(media_dir, new_name)
                assert os.path.exists(old_file_path)

                # print(old_file_path)
                # print(photo.image.name)
                # print(new_file_path)
                # print(new_name)

                os.makedirs(os.path.split(new_file_path)[0], exist_ok=True)
                move(old_file_path, new_file_path)
                # copyfile(old_file_path, new_file_path)
                image.name = new_name

            if not os.listdir(old_dir):
                os.rmdir(old_dir)

            photo.save()
