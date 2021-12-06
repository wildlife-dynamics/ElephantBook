from django import forms
from django.conf import settings
from django.contrib.contenttypes.models import ContentType

from .models import *
from eb_core.forms import Seek_Identity_Form, Elephant_Voices_Identity_Form


class Assignment_Form(forms.ModelForm):
    """Form for modifying fields of an `Assignment` object."""
    class Meta:
        model = Assignment
        fields = ('completed', 'needs_review', 'notes')
