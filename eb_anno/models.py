from django.core.exceptions import ValidationError
from django.db import models

from eb_core.models import (
    Bounding_Box,
    EBUser,
    Elephant_Voices_Identity,
    Photo,
    Seek_Identity,
)


class EB_Anno_Permisson(models.Model):
    class Meta:
        managed = False

        default_permissions = ()

        permissions = (
            ("main", "Access bulk annotation portion of EB"),
            ("advanced", "Access advanced features not intended for typical EB use"),
        )


class Annotation_Target(models.Model):
    """Model representing an individual to be annotated."""

    job_name = models.CharField(max_length=128, null=True, blank=True)
    datetime = models.DateTimeField(null=True, blank=True)
    name = models.CharField(max_length=128, null=True, blank=True)
    json = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"{self.job_name} - {self.name}"


class Annotation_Target_Photo(Photo):
    """Model representing a photo associated with an `Annotation_Target` object."""

    annotation_target = models.ForeignKey("Annotation_Target", on_delete=models.CASCADE)


class Assignment(models.Model):
    """Model representing an annotation job assigned to a user."""

    annotation_target = models.ForeignKey("Annotation_Target", on_delete=models.CASCADE)
    job_name = models.CharField(max_length=128, null=True, blank=True)
    users = models.ManyToManyField(EBUser, blank=True)
    completed = models.BooleanField(default=False)
    needs_review = models.BooleanField(default=False)

    seek_identity = models.ForeignKey(Seek_Identity, null=True, blank=True, on_delete=models.PROTECT)
    elephant_voices_identity = models.ForeignKey(
        Elephant_Voices_Identity, null=True, blank=True, on_delete=models.PROTECT
    )

    json = models.JSONField(null=True, blank=True)
    notes = models.TextField(default="", blank=True)

    def __str__(self):
        return f"{ self.pk } - { self.annotation_target }"


class Assignment_Bounding_Box(Bounding_Box):
    """Model representing a bounding box of an elephant associated with an `Assignment`."""

    assignment = models.ForeignKey("Assignment", on_delete=models.CASCADE)

    def save(self, *args, **kwargs):
        if type(self.photo) is not Annotation_Target_Photo:
            raise ValidationError("self.photo is not of type Annotation_Target_Photo")

        super().save(*args, **kwargs)
