from django.db import models

from eb_core.models import *


class Photo_ML(models.Model):
    """Model representing ML data for a Photo object."""
    photo = models.OneToOneField('eb_core.Photo', on_delete=models.CASCADE, null=True, blank=True)

    ear_detections = models.JSONField(null=True, blank=True)
