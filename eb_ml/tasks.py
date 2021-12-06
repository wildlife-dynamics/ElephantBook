from django.core.exceptions import ObjectDoesNotExist

from celery import shared_task

import os
from PIL import Image
import torch
import torchvision

from .models import *
from eb_core.models import *

EAR_CLASS_MAP = {
    1: 'Left Ear',
    2: 'Right Ear',
}


@shared_task
def detect_ears(photos_ids):
    return
    photos = Photo.objects.filter(pk__in=photos_ids)

    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    device = 'cpu'

    model = torch.load(os.path.join(os.path.dirname(__file__), 'static/ear_detector'), device)

    model.eval()

    transforms = torchvision.transforms.Compose([
        torchvision.transforms.Resize((900, 900)),
        torchvision.transforms.ToTensor(),
    ])

    for photo in photos:
        try:
            instance = photo.photo_ml
            if instance.ear_detections is not None:
                continue
        except ObjectDoesNotExist:
            instance = Photo_ML()
            instance.photo = photo

        img = Image.open(f'media/{photo.image.name}')

        with torch.no_grad():
            outputs = model(torch.unsqueeze(transforms(img), 0).to(device))[0]

        for k, v in outputs.items():
            outputs[k] = v.cpu().numpy()

        boxes = outputs['boxes'] / 900
        boxes[:, 2] -= boxes[:, 0]
        boxes[:, 3] -= boxes[:, 1]
        outputs['boxes'] = boxes

        for k, v in outputs.items():
            outputs[k] = v.tolist()

        instance.ear_detections = outputs
        instance.save()
