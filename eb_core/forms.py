from django import forms
from django.conf import settings

from .models import *

from datetime import datetime
import json
import requests


class EarthRanger_Sighting_Create_Form(forms.ModelForm):
    """Form for creating a `Group_Sighting` object from an EarthRanger event."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        NUM_EVENTS = 30

        endpoint = f'{settings.ER_MAIN}events?event_type={settings.ER_EVENT_TYPE}&state=new&state=active&page_size={NUM_EVENTS}'
        headers = {'Authorization': f'Bearer {settings.BEARER}'}
        rsp = requests.get(endpoint, headers=headers)
        events = [
            event for event in rsp.json()['data']['results']
            if not EarthRanger_Sighting.objects.filter(earthranger_serial=event['serial_number']).exists()
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
        model = EarthRanger_Sighting
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
        fields = ('unphotographed_individuals', )
        widgets = {
            'unphotographed_individuals': forms.CheckboxSelectMultiple,
        }


class Group_Sighting_Notes_Form(forms.ModelForm):
    """Form for modifying the `notes` field on a `Group_Sighting` object."""
    class Meta:
        model = Group_Sighting
        fields = ('notes', )


class Seek_Identity_Form(forms.ModelForm):
    """Form for creating/modifying a `Seek_Identity`."""
    class Meta:
        model = Seek_Identity
        exclude = ('individual_sighting', )

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
        exclude = ('individual_sighting', )

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
        fields = ('individual', )


InjuryFormSet = forms.modelformset_factory(Injury, exclude=('individual_sighting', ), extra=0, can_delete=True)


class Search_Form(forms.ModelForm):
    """Form for performing an `Individual_Sighting` search."""
    class Meta:
        model = Search_Model
        exclude = ('individual_sighting', )


class Individual_Sighting_Form(forms.ModelForm):
    """Form for modifying various attributes on an `Individual_Sighting` object."""
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

    class Meta:
        model = Individual_Sighting
        exclude = ('individual', 'group_sighting', 'seek_identity')


class Combine_Individual_Form(forms.Form):
    """Form for combining two `Individual` objects. 
    All `Individual_Sighting` objects associated with `duplicate` are reassigned to `correct` and `duplicate` is deleted.
    """
    correct = forms.ModelChoiceField(queryset=Individual.objects.all().order_by('name'))
    duplicate = forms.ModelChoiceField(queryset=Individual.objects.all().order_by('name'))

    def save(self):
        correct = self.cleaned_data['correct']
        duplicate = self.cleaned_data['duplicate']

        assert correct != duplicate

        # Transfer Individual Sighting objects
        for individual_sighting in duplicate.individual_sighting_set.all():
            individual_sighting.individual = correct
            individual_sighting.save()

        # Transfer Individual Photo objects
        for individual_photo in duplicate.individual_photo_set.all():
            individual_photo.individual = correct
            individual_photo.save()

        # Transfer notes
        if duplicate.notes:
            correct.notes += f'\nAutomatically copied notes from Individual {duplicate.pk}: ' + duplicate.notes
            correct.save()

        duplicate.delete()


class Individual_Profile_Form(forms.Form):
    """Form for modifying the `profile` fields on an `Individual` object."""
    photos = forms.ChoiceField(required=False)

    def __init__(self, individual, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['photos'].choices = [(None, '----')] + \
                                        [(f'individual_photo {photo.pk}', str(photo))
                                         for photo in individual.individual_photo_set.all()] + \
                                        [(f'sighting_photo {bounding_box.photo.pk}', str(bounding_box.photo))
                                         for individual_sighting in individual.individual_sighting_set.all()
                                         for bounding_box in individual_sighting.sighting_bounding_box_set.all()]

        if isinstance(individual.profile, Individual_Photo):
            self.fields['photos'].initial = f'individual_photo {individual.profile_id}'
        elif isinstance(individual.profile, Sighting_Photo):
            self.fields['photos'].initial = f'sighting_photo {individual.profile_id}'

    def save(self, individual):
        pk = self.cleaned_data['photos'].split(' ')[-1]

        if pk:
            individual.profile = Photo.objects.get(pk=int(pk))
        else:
            individual.profile = None

        individual.save()


class Individual_Notes_Form(forms.ModelForm):
    """Form for modifying the `notes` field on an `Individual` object."""
    class Meta:
        model = Individual
        fields = ('notes', )


def subgroup_sighting_formset_constructor(group_sighting):
    class Subgroup_Sighting_Form(forms.ModelForm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['individual_sightings'].choices = [
                (individual_sighting.pk, individual_sighting)
                for individual_sighting in group_sighting.individual_sighting_set.all()
            ]
            self.fields['unphotographed_individuals'].choices = [
                (individual.pk, individual) for individual in group_sighting.unphotographed_individuals.all()
            ]

        class Meta:
            model = Subgroup_Sighting
            exclude = ('group_sighting', )

    return forms.modelformset_factory(Subgroup_Sighting,
                                      form=Subgroup_Sighting_Form,
                                      exclude=('group_sighting', ),
                                      extra=0,
                                      can_delete=True,
                                      widgets={
                                          'individual_sightings': forms.CheckboxSelectMultiple,
                                          'unphotographed_individuals': forms.CheckboxSelectMultiple,
                                      })


class Subgroup_Sighting_Notes_Form(forms.ModelForm):
    """Form for modifying the `notes` field on a `Subgroup_Sighting` object."""
    class Meta:
        model = Subgroup_Sighting
        fields = ('notes', )


class EBUser_Create_Form(forms.ModelForm):
    class Meta:
        model = EBUser
        fields = ['first_name', 'last_name', 'email', 'username', 'password', 'groups']
        widgets = {'password': forms.PasswordInput()}

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user
