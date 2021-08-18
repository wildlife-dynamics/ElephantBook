from django import forms
from django.conf import settings
from django.contrib.contenttypes.models import ContentType

from .models import *

from datetime import datetime
import json
import requests


class Add_Group_Sighting_Form(forms.ModelForm):
    """Form for creating a `Group_Sighting` object from an EarthRanger event."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        NUM_EVENTS = 30

        endpoint = f'{settings.ER_MAIN}events?event_type={settings.ER_EVENT_TYPE}&state=new&state=active&page_size={NUM_EVENTS}'
        headers = {'Authorization': f'Bearer {settings.BEARER}'}
        rsp = requests.get(endpoint, headers=headers)
        events = [
            event for event in rsp.json()['data']['results']
            if not Group_Sighting.objects.filter(earthranger_serial=event['serial_number']).exists()
        ]
        events = sorted(events, key=lambda k: -k['serial_number'])

        for event in events:
            if event['location'] is None or event['time'] is None:
                event['serial_number'] = f'{event["serial_number"]} INVALID EVENT'

        self.fields['earthranger_event'] = forms.ChoiceField(choices=[(
            json.dumps(event), f'Serial: {event["serial_number"]}, '
            f'Reported by: { event["reported_by"]["username"] if event["reported_by"] and "username" in event["reported_by"] else "Unknown"}'
        ) for event in events],
            widget=forms.RadioSelect,
            required=True)

    class Meta:
        model = Group_Sighting
        fields = []

    def save(self, commit=True):
        instance = super().save(commit=False)
        earthranger_event = json.loads(self.cleaned_data.get('earthranger_event'))

        instance.earthranger_serial = earthranger_event['serial_number']
        instance.earthranger_id = earthranger_event['id']
        instance.lat = earthranger_event['location']['latitude']
        instance.lon = earthranger_event['location']['longitude']
        try:
            instance.datetime = datetime.strptime(earthranger_event['time'], '%Y-%m-%dT%H:%M:%S.%f%z')
        except:
            instance.datetime = datetime.strptime(earthranger_event['time'], '%Y-%m-%dT%H:%M:%S%z')

        instance.json = earthranger_event

        instance.save()

        return instance


class Multi_Image_Form(forms.Form):
    """Form for uploading multiple images."""
    images = forms.ImageField(required=False, widget=forms.ClearableFileInput(attrs={'multiple': True}))


class Group_Sighting_Unphotographed_Individuals_Form(forms.ModelForm):
    """Form for modifying the `notes` field on a `Group_Sighting` object."""
    class Meta:
        model = Group_Sighting
        fields = ('unphotographed_individuals',)
        widgets = {
            'unphotographed_individuals': forms.CheckboxSelectMultiple,
        }


class Group_Sighting_Notes_Form(forms.ModelForm):
    """Form for modifying the `notes` field on a `Group_Sighting` object."""
    class Meta:
        model = Group_Sighting
        fields = ('notes',)


class Seek_Identity_Form(forms.ModelForm):
    """Form for creating/modifying a `Seek_Identity`."""
    class Meta:
        model = Seek_Identity
        exclude = ('individual_sighting',)

    def save(self, individual_sighting=None, commit=True):
        instance = super().save(commit=False)
        instance.individual_sighting = individual_sighting
        if commit:
            instance.save()
        return instance


class Elephant_Voices_Identity_Form(forms.ModelForm):
    """Form for creating/modifying an `Elephant_Voices_Identity` object."""
    class Meta:
        model = Elephant_Voices_Identity
        exclude = ('individual_sighting',)

    def save(self, individual_sighting=None, commit=True):
        instance = super(Elephant_Voices_Identity_Form, self).save(commit=False)
        instance.individual_sighting = individual_sighting
        if commit:
            instance.save()
        return instance


class Set_Identity_Form(forms.ModelForm):
    """Form for assigning an `Individual` to an `Individual_Sighting`.
       Also handles attribute propagation from the most recent `Individual_Sighting` object."""
    auto_propagate_seek = forms.BooleanField(required=False)
    auto_propagate_injuries = forms.BooleanField(required=False)

    class Meta:
        model = Individual_Sighting
        fields = ('individual',)


InjuryFormSet = forms.modelformset_factory(Injury, exclude=('individual_sighting',), extra=0, can_delete=True)


class Search_Form(forms.ModelForm):
    """Form for performing an `Individual_Sighting` search."""
    class Meta:
        model = Search_Model
        exclude = ('individual_sighting',)


class Individual_Sighting_Form(forms.ModelForm):
    """Form for modifying various attributes on an `Individual_Sighting` object."""

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['expert_reviewed'].disabled = user is None or user.is_anonymous or not user.expert

    class Meta:
        model = Individual_Sighting
        exclude = ('individual', 'group_sighting')


class Add_Individual_Form(forms.ModelForm):
    """Form for creating an `Individual` object."""
    class Meta:
        model = Individual
        fields = ('name',)


class Combine_Individual_Form(forms.Form):
    """Form for combining two `Individual` objects. 
    All `Individual_Sighting` objects associated with `individual_2` are reassigned to `individual_1` and `individual_2` is deleted.
    """
    individual_1 = forms.ModelChoiceField(queryset=Individual.objects.all().order_by('name'))
    individual_2 = forms.ModelChoiceField(queryset=Individual.objects.all().order_by('name'))


class Individual_Profile_Form(forms.Form):
    """Form for modifying the `profile` fields on an `Individual` object."""
    photos = forms.ChoiceField(required=False)

    def __init__(self, individual, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['photos'].choices = [(None, '----')] + \
                                        [(f'individual_photo {photo.id}', str(photo))
                                         for photo in individual.individual_photo_set.all()] + \
                                        [(f'sighting_photo {bounding_box.photo.id}', str(bounding_box.photo))
                                         for individual_sighting in individual.individual_sighting_set.all()
                                         for bounding_box in individual_sighting.sighting_bounding_box_set.all()]

        if individual.profile_type == ContentType.objects.get_for_model(Individual_Photo):
            self.fields['photos'].initial = f'individual_photo {individual.profile_id}'
        elif individual.profile_type == ContentType.objects.get_for_model(Sighting_Photo):
            self.fields['photos'].initial = f'sighting_photo {individual.profile_id}'


class Individual_Notes_Form(forms.ModelForm):
    """Form for modifying the `notes` field on an `Individual` object."""
    class Meta:
        model = Individual
        fields = ('notes',)


def social_sighting_formset_constructor(group_sighting):
    class Social_Sighting_Form(forms.ModelForm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['individual_sightings'].choices = [
                (individual_sighting.id, individual_sighting)
                for individual_sighting in group_sighting.individual_sighting_set.all()
            ]
            self.fields['unphotographed_individuals'].choices = [
                (individual.id, individual)
                for individual in group_sighting.unphotographed_individuals.all()
            ]

        class Meta:
            model = Social_Sighting
            exclude = ('group_sighting',)

    return forms.modelformset_factory(
        Social_Sighting, form=Social_Sighting_Form, exclude=('group_sighting',), extra=0, can_delete=True, widgets={
            'individual_sightings': forms.CheckboxSelectMultiple,
            'unphotographed_individuals': forms.CheckboxSelectMultiple,
        })


class Social_Sighting_Notes_Form(forms.ModelForm):
    """Form for modifying the `notes` field on a `Social_Sighting` object."""
    class Meta:
        model = Social_Sighting
        fields = ('notes',)
