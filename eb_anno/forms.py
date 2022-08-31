from django import forms

from .models import Assignment


class Assignment_Form(forms.ModelForm):
    """Form for modifying fields of an `Assignment` object."""

    class Meta:
        model = Assignment
        fields = ("completed", "needs_review", "notes")
