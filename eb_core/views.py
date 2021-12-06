from django.apps import apps
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
import django.db.models.fields
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.views import generic

from .forms import *
from .models import *
from .tasks import *
from .utils import *
if apps.is_installed('eb_ml'):
    from eb_ml.tasks import *

from collections import defaultdict
import json
import numpy as np
import os
import pandas as pd


class Index_View(LoginRequiredMixin, generic.TemplateView):
    template_name = 'index.html'
    extra_context = {'title': 'Home'}


class Group_Sighting_List(PermissionRequiredMixin, generic.ListView):
    permission_required = 'eb_core.advanced'
    model = Group_Sighting
    ordering = '-datetime'
    paginate_by = 100
    template_name = 'group_sighting/list.html'


class Group_Sighting_Create(PermissionRequiredMixin, generic.CreateView):
    permission_required = 'eb_core.advanced'
    model = Group_Sighting
    fields = ('lat', 'lon', 'datetime', 'notes')
    template_name = 'form.html'

    def get_success_url(self):
        return reverse('group sighting view', kwargs={'pk': self.object.pk})


class Group_Sighting_View(PermissionRequiredMixin, generic.DetailView):
    permission_required = 'eb_core.advanced'
    model = Group_Sighting
    template_name = 'group_sighting/view.html'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()

        if type(self) is Group_Sighting_View:
            if isinstance(self.object, EarthRanger_Sighting):
                return redirect('earthranger sighting view', earthranger_serial=self.object.earthranger_serial)

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        group_sighting_photo_set = self.object.sighting_photo_set.all()

        images = [{
            'id': photo.image.name,
            'url': photo.compressed_image.url,
            'full_res': reverse('view media', args=(photo.image.name, )),
        } for photo in group_sighting_photo_set]

        individual_sighting_categories = {k: k.pk for i, k in enumerate(self.object.individual_sighting_set.all(), 1)}

        boxes = {
            photo.image.name: [{
                'bbox': [bbox.x, bbox.y, bbox.w, bbox.h],
                'category_id': individual_sighting_categories[bbox.individual_sighting],
                'bbox_id': bbox.pk,
            } for bbox in photo.bounding_box_set.all()]
            for photo in group_sighting_photo_set
        }

        categories = [{'id': i, 'name': f'Individual Sighting {i}'} for i in individual_sighting_categories.values()]

        thumbnails = {
            '': {i: Sighting_Photo.objects.get(image=image['id']).thumbnail.url
                 for i, image in enumerate(images)}
        }

        context |= {
            # Form for creating `Sighting_Photo` objects
            'form':
            Multi_Image_Form(),
            # Form for modifying associated `notes`
            'notes_form':
            Group_Sighting_Notes_Form(instance=self.object),
            # Images associated with the `Group_Sighting` object
            'images':
            json.dumps(images),
            # JSON bounding boxes for the image viewer
            'boxes':
            json.dumps(boxes),
            # Annotation categories for all associated `Individual_Sighting` objects
            'categories':
            json.dumps(categories),
            # Thumbnails associated with the `Group_Sighting` object
            'thumbnails':
            thumbnails,
            # Form for creating/modifying `Subgroup_Sighting` objects
            'subgroup_sighting_formset':
            subgroup_sighting_formset_constructor(self.object)(queryset=self.object.subgroup_sighting_set.all()),
            # Form for recording unphotographed `Individual` objects
            'unphotographed_individuals_form':
            Group_Sighting_Unphotographed_Individuals_Form(instance=self.object),
        }

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Edit Bounding Boxes
        if request.POST.get('boxes'):
            new_boxes = json.loads(request.POST.get('boxes'))

            individual_sightings = {
                individual_sighting.pk: individual_sighting
                for individual_sighting in self.object.individual_sighting_set.all()
            }

            old_boxes = {
                bbox.pk: bbox
                for individual_sighting in self.object.individual_sighting_set.all()
                for bbox in individual_sighting.sighting_bounding_box_set.all()
            }

            for sighting_photo in self.object.sighting_photo_set.all():
                for box in new_boxes[sighting_photo.image.name]:
                    if 'bbox_id' in box:
                        old_box = old_boxes[box['bbox_id']]
                        old_box.x = box['bbox'][0]
                        old_box.y = box['bbox'][1]
                        old_box.w = box['bbox'][2]
                        old_box.h = box['bbox'][3]
                        old_box.save()
                        del old_boxes[box['bbox_id']]
                    else:
                        if box['category_id'] not in individual_sightings:
                            individual_sighting = Individual_Sighting(group_sighting=self.object)
                            individual_sighting.save()
                            individual_sightings[box['category_id']] = individual_sighting

                        individual_sighting = individual_sightings[box['category_id']]

                        Sighting_Bounding_Box(individual_sighting=individual_sighting,
                                              photo=sighting_photo,
                                              x=box['bbox'][0],
                                              y=box['bbox'][1],
                                              w=box['bbox'][2],
                                              h=box['bbox'][3]).save()

            for box in old_boxes.values():
                individual_sighting = box.individual_sighting
                box.delete()
                if not individual_sighting.sighting_bounding_box_set.all():
                    individual_sighting.delete()

        # Add Photos (After Bounding Box Edit on Current Photos)
        form = Multi_Image_Form(request.POST, request.FILES)
        if form.is_valid():
            for image in request.FILES.getlist('images'):
                instance = Sighting_Photo(image=image,
                                          compressed_image=compress_image(image),
                                          thumbnail=compress_image(image, maxw=100, prefix='thumbnail'),
                                          group_sighting=self.object)

                upload_to = self.object.get_upload_to()

                instance.image_name = f'{upload_to}/{instance.image.name}'
                instance.image.field.upload_to = upload_to
                instance.compressed_image.field.upload_to = upload_to
                instance.thumbnail.field.upload_to = upload_to

                try:
                    instance.save()
                except IntegrityError as e:
                    # Discard photos with duplicate names
                    print(instance.image_name, e)
                    continue
            if apps.is_installed('eb_ml'):
                detect_ears.delay(list(self.object.sighting_photo_set.values_list('pk', flat=True)))

        # Notes
        form = Group_Sighting_Notes_Form(request.POST, instance=self.object)
        if form.is_valid():
            form.save()

        # Unphotographed Individuals
        form = Group_Sighting_Unphotographed_Individuals_Form(request.POST, instance=self.object)
        if form.is_valid():
            form.save()

        # Subgroup Sightings
        formset = subgroup_sighting_formset_constructor(self.object)(request.POST)
        for form in formset:
            if form.is_valid():
                instance = form.save(commit=False)
                if 'DELETE' in form.cleaned_data and form.cleaned_data['DELETE']:
                    if instance.pk is not None:
                        instance.delete()
                else:
                    instance.group_sighting = self.object
                    instance.save()
                    form.save_m2m()

        return HttpResponseRedirect(self.request.path_info)


class EarthRanger_Sighting_List(Group_Sighting_List):
    permission_required = 'eb_core.main'
    model = EarthRanger_Sighting
    ordering = '-earthranger_serial'
    template_name = 'group_sighting/earthranger_sighting/list.html'


class EarthRanger_Sighting_Create(PermissionRequiredMixin, generic.CreateView):
    permission_required = 'eb_core.main'
    form_class = EarthRanger_Sighting_Create_Form
    model = EarthRanger_Sighting
    template_name = 'form.html'

    def get_success_url(self):
        return reverse('earthranger sighting view', kwargs={'earthranger_serial': self.object.earthranger_serial})


class EarthRanger_Sighting_View(Group_Sighting_View):
    permission_required = 'eb_core.main'
    model = EarthRanger_Sighting
    template_name = 'group_sighting/earthranger_sighting/view.html'

    def get_object(self, **kwargs):
        return EarthRanger_Sighting.objects.get(earthranger_serial=self.kwargs['earthranger_serial'])


class Subgroup_Sighting_List(PermissionRequiredMixin, generic.ListView):
    permission_required = 'eb_core.main'
    model = Subgroup_Sighting
    ordering = '-group_sighting__datetime'
    paginate_by = 100
    template_name = 'subgroup_sighting/list.html'


class Subgroup_Sighting_View(PermissionRequiredMixin, generic.DetailView):
    permission_required = 'eb_core.advanced'
    model = Subgroup_Sighting
    template_name = 'subgroup_sighting/view.html'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        bbox_set = [
            bbox for individual_sighting in self.object.individual_sightings.all()
            for bbox in individual_sighting.sighting_bounding_box_set.all()
        ]

        images = list({
            bbox.photo.image.name: {
                'id': bbox.photo.image.name,
                'url': bbox.photo.compressed_image.url,
                'full_res': bbox.photo.image.url
            }
            for bbox in bbox_set
        }.values())

        individual_sighting_categories = {k: k.pk for i, k in enumerate(self.object.individual_sightings.all(), 1)}

        boxes = defaultdict(list)
        for bbox in bbox_set:
            boxes[bbox.photo.image.name].append({
                'bbox': [bbox.x, bbox.y, bbox.w, bbox.h],
                'category_id': individual_sighting_categories[bbox.individual_sighting],
                'bbox_id': bbox.pk,
            })

        categories = [{'id': i, 'name': f'Individual Sighting {i}'} for i in individual_sighting_categories.values()]

        thumbnails = {
            '': {i: Sighting_Photo.objects.get(image=image['id']).thumbnail.url
                 for i, image in enumerate(images)}
        }

        context |= {
            # Form for modifying associated `notes`
            'form': Subgroup_Sighting_Notes_Form(instance=self.object),
            # Images associated with the `Group_Sighting` object
            'images': json.dumps(images),
            # JSON bounding boxes for the image viewer
            'boxes': json.dumps(boxes),
            # Annotation categories for all associated `Individual_Sighting` objects
            'categories': json.dumps(categories),
            # Thumbnails associated with the `Subgroup_Sighting` object
            'thumbnails': thumbnails,
        }

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        form = Subgroup_Sighting_Notes_Form(request.POST, instance=self.object)
        if form.is_valid():
            form.save()

        return HttpResponseRedirect(self.request.path_info)


class Individual_Sighting_List(PermissionRequiredMixin, generic.ListView):
    permission_required = 'eb_core.main'
    model = Individual_Sighting
    ordering = '-group_sighting__datetime'
    paginate_by = 100
    template_name = 'individual_sighting/list.html'


class Individual_Sighting_Individual_List(Individual_Sighting_List):
    permission_required = 'eb_core.main'

    def get_queryset(self):
        return super().get_queryset().filter(individual__pk=self.kwargs['pk'])


class Individual_Sighting_Queue(Individual_Sighting_List):
    permission_required = 'eb_core.main'
    ordering = 'group_sighting__datetime'

    def get_queryset(self):
        return super().get_queryset().filter(completed=False)


class Individual_Sighting_Expert_Queue(Individual_Sighting_List):
    permission_required = 'eb_core.main'
    ordering = 'group_sighting__datetime'

    def get_queryset(self):
        return super().get_queryset().filter(completed=True, expert_reviewed=False)


class Individual_Sighting_Unidentified_List(Individual_Sighting_List):
    permission_required = 'eb_core.main'
    ordering = '-group_sighting__datetime'

    def get_queryset(self):
        return super().get_queryset().exclude(individual__isnull=False).exclude(unidentifiable=True)


class Individual_Sighting_View(PermissionRequiredMixin, generic.DetailView):
    permission_required = 'eb_core.main'
    model = Individual_Sighting
    template_name = 'individual_sighting/view.html'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        bbox_set = self.object.sighting_bounding_box_set.all()

        images = [{
            'id': bbox.photo.image.name,
            'url': bbox.photo.compressed_image.url,
            'full_res': reverse('view media', args=(bbox.photo.image.name, )),
        } for bbox in bbox_set]

        boxes = {
            bbox.photo.image.name: [{
                'bbox': [bbox.x, bbox.y, bbox.w, bbox.h],
                'category_id': self.object.pk
            }]
            for bbox in bbox_set
        }

        thumbnails = {
            '': {i: Sighting_Photo.objects.get(image=image['id']).thumbnail.url
                 for i, image in enumerate(images)}
        }

        context |= {
            # Images associated with the `Individual_Sighting` object
            'images': json.dumps(images),
            # JSON bounding boxes for the image viewer
            'boxes': json.dumps(boxes),
            # Annotation category for the`Individual_Sighting`
            'categories': json.dumps([{
                'id': self.object.pk,
                'name': f'Individual Sighting {self.object.pk}'
            }]),
            # Form for assigning an `Individual` to the `Individual_Sighting` object
            'set_identity_form': Set_Identity_Form(instance=self.object),
            # Form for creating/modifying associated `Injury` objects
            'injury_formset': InjuryFormSet(queryset=self.object.injury_set.all()),
            # Thumbnails associated with the `Individual_Sighting` object
            'thumbnails': thumbnails,
            # Form for modifying various attributes of the `Individual_Sighting` object
            'form': Individual_Sighting_Form(instance=self.object, user=self.request.user),
        }
        # Form for creating/modifying the associated `SEEK_Identity` object
        try:
            context['edit_seek_form'] = Seek_Identity_Form(instance=self.object.seek_identity)
        except ObjectDoesNotExist:
            context['edit_seek_form'] = Seek_Identity_Form()

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # SEEK
        try:
            form = Seek_Identity_Form(request.POST, instance=self.object.seek_identity)
        except ObjectDoesNotExist:
            form = Seek_Identity_Form(request.POST)

        if form.is_valid():
            form.save(self.object)

        # Various Individual Sighting Attributes
        form = Individual_Sighting_Form(request.POST, instance=self.object, user=request.user)
        if form.is_valid():
            form.save()

        # Injuries
        formset = InjuryFormSet(request.POST)
        for form in formset:
            if form.is_valid():
                instance = form.save(commit=False)
                if 'DELETE' in form.cleaned_data and form.cleaned_data['DELETE']:
                    if instance.pk is not None:
                        instance.delete()
                else:
                    instance.individual_sighting = self.object
                    instance.save()

        # Identity
        form = Set_Identity_Form(request.POST, instance=self.object)
        if form.is_valid():
            form.save()
            if self.object.individual and self.object.individual.individual_sighting_set.count() > 1:
                last_individual_sighting = self.object.individual.individual_sighting_set.all().order_by('-pk')[1]

                # Propagate SEEK
                if form.cleaned_data['auto_propagate_seek']:
                    seek_identity = self.object.seek_identity
                    last_seek_identity = last_individual_sighting.seek_identity
                    for field in Seek_Identity._meta.get_fields():
                        if type(field) == django.db.models.fields.CharField:
                            if getattr(seek_identity, field.name) is None:
                                setattr(seek_identity, field.name, getattr(last_seek_identity, field.name))
                    seek_identity.save()

                # Propagate Injuries
                if form.cleaned_data['auto_propagate_injuries'] and not self.object.injury_set.exists():
                    for injury in last_individual_sighting.injury_set.all():
                        injury.pk = None
                        injury.individual_sighting = self.object
                        injury.save()

        return HttpResponseRedirect(self.request.path_info)


class Individual_List(PermissionRequiredMixin, generic.ListView):
    permission_required = 'eb_core.main'
    model = Individual
    ordering = '-pk'
    paginate_by = 100
    template_name = 'individual/list.html'


class Individual_Create(PermissionRequiredMixin, generic.CreateView):
    permission_required = 'eb_core.main'
    model = Individual
    fields = ['name', 'notes']
    template_name = 'form.html'

    def get_success_url(self):
        return reverse('individual view', kwargs={'pk': self.object.pk})


class Individual_Combine(PermissionRequiredMixin, generic.FormView):
    permission_required = 'eb_core.main'
    form_class = Combine_Individual_Form
    success_url = '.'
    template_name = 'form.html'

    def form_valid(self, form):
        form.save()
        return super().form_valid(form)


class Individual_View(PermissionRequiredMixin, generic.DetailView):
    permission_required = 'eb_core.main'
    model = Individual
    template_name = 'individual/view.html'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            last_individual_sighting = self.object.individual_sighting_set.latest()
        except Individual_Sighting.DoesNotExist:
            last_individual_sighting = None

        individual_photo_set = self.object.individual_photo_set.all()
        images = [{
            'id': photo.image.name,
            'url': photo.compressed_image.url,
            'full_res': reverse('view media', args=(photo.image.name, )),
        } for photo in individual_photo_set]

        boxes = {
            photo.image.name: [{
                'bbox': [bbox.x, bbox.y, bbox.w, bbox.h],
                'category_id': self.object.pk,
            } for bbox in photo.bounding_box_set.all()]
            for photo in individual_photo_set
        }

        thumbnails = {
            'Individual':
            {i: Individual_Photo.objects.get(image=image['id']).thumbnail.url
             for i, image in enumerate(images)}
        }
        image_index = len(thumbnails['Individual'])

        individual_sighting_bbox_set = [
            bbox for individual_sighting in self.object.individual_sighting_set.all()
            for bbox in individual_sighting.sighting_bounding_box_set.all()
        ]

        images += [{
            'id': bbox.photo.image.name,
            'url': bbox.photo.compressed_image.url,
            'full_res': reverse('view media', args=(bbox.photo.image.name, )),
        } for bbox in individual_sighting_bbox_set]

        boxes.update({
            bbox.photo.image.name: [{
                'bbox': [bbox.x, bbox.y, bbox.w, bbox.h],
                'category_id': self.object.pk
            }]
            for bbox in individual_sighting_bbox_set
        })

        for individual_sighting in self.object.individual_sighting_set.all():
            thumbnails[individual_sighting.group_sighting.pk] = {
                i + image_index: bbox.photo.thumbnail.url
                for i, bbox in enumerate(individual_sighting.sighting_bounding_box_set.all())
            }
            image_index += len(thumbnails[individual_sighting.group_sighting.pk])

        context |= {
            # Latest `Individual_Sighting` associated with the `Individual` object
            'last_individual_sighting': last_individual_sighting,
            # Form for creating `Individual_Photo` objects
            'form': Multi_Image_Form(),
            # Form for modifying associated `notes`
            'notes_form': Individual_Notes_Form(instance=self.object),
            # Images associated with the `Individual` object
            'images': json.dumps(images),
            # JSON boudning boxes for the image viewer
            'boxes': json.dumps(boxes),
            # Annotation category for the (single) `Individual`
            'categories': json.dumps([{
                'id': self.object.pk,
                'name': f'{self.object.name}'
            }]),
            # Thumbnails associated with the `Individual_Sighting` object
            'thumbnails': thumbnails,
            # Form to set the `profile` attribute of the `Individual`
            'profile_form': Individual_Profile_Form(self.object),
        }

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Edit Bounding Boxes
        if request.POST.get('boxes'):
            boxes = json.loads(request.POST.get('boxes'))

            self.object.individual_bounding_box_set.all().delete()

            for individual_photo in self.object.individual_photo_set.all():
                for box in boxes[individual_photo.image.name]:
                    Individual_Bounding_Box(individual=self.object,
                                            photo=individual_photo,
                                            x=box['bbox'][0],
                                            y=box['bbox'][1],
                                            w=box['bbox'][2],
                                            h=box['bbox'][3]).save()

        # Add Photos (After Bounding Box Edit on Current Photos)
        form = Multi_Image_Form(request.POST, request.FILES)
        if form.is_valid():
            for image in request.FILES.getlist('images'):
                instance = Individual_Photo(image=image,
                                            compressed_image=compress_image(image),
                                            thumbnail=compress_image(image, maxw=100, prefix='thumbnail'),
                                            individual=self.object)

                upload_to = f'individual/{self.object.pk}'
                instance.image_name = f'{upload_to}/{instance.image.name}'
                instance.image.field.upload_to = upload_to
                instance.compressed_image.field.upload_to = upload_to
                instance.thumbnail.field.upload_to = upload_to
                try:
                    instance.save()
                except IntegrityError as e:
                    # Discard photos with duplicate names
                    print(instance.image_name, e)
                    continue

        # Profile
        form = Individual_Profile_Form(self.object, request.POST)
        if form.is_valid():
            form.save(self.object)

        # Notes
        form = Individual_Notes_Form(request.POST, instance=self.object)
        if form.is_valid():
            form.save()

        return HttpResponseRedirect(self.request.path_info)


class Seek_Search_View(PermissionRequiredMixin, generic.TemplateView):
    permission_required = 'eb_core.main'
    template_name = 'search/seek.html'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        given_code = Seek_Identity_Form(self.request.GET).save(commit=False)

        individuals = Individual.objects.filter(individual_sighting__isnull=False).distinct()
        if individuals.count() == 0:
            return redirect('index')

        seek_identities = get_latest_seek_identities(individuals)
        seek_codes = [np.array(seek_identity) for seek_identity in seek_identities]

        binary = 'binary' in self.request.GET and self.request.GET['binary'] == 'on'
        seek_scores = seek_score(given_code, seek_codes, binary=binary)

        results = pd.DataFrame({
            'individual': individuals,
            'seek_code': seek_codes,
            'seek_score': seek_scores,
        }).dropna().sort_values('seek_score', ascending=False, ignore_index=True)

        context |= {
            'form': Search_Form(instance=Search_Form(self.request.GET).save(commit=False)),
            'results': results,
        }

        return context


class Match_View(PermissionRequiredMixin, generic.DetailView):
    permission_required = 'eb_core.main'
    model = Individual_Sighting
    template_name = 'search/view.html'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        results = score(self.object)

        context |= {
            'results': results,
        }

        return context


class Stats_View(PermissionRequiredMixin, generic.TemplateView):
    permission_required = 'eb_core.advanced'
    template_name = 'stats/index.html'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        context |= {
            'num_group_sightings': Group_Sighting.objects.count(),
            'num_individuals': Individual.objects.count(),
            'num_individual_sightings': Individual_Sighting.objects.count(),
            'num_sighting_photos': Sighting_Photo.objects.count(),
            'num_sighting_bounding_boxes': Sighting_Bounding_Box.objects.count(),
        }

        return context


class Media_View(LoginRequiredMixin, generic.TemplateView):
    template_name = 'view_media/index.html'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        context |= {
            'url': os.path.join(settings.MEDIA_URL, kwargs['name']),
        }

        return context


class EBUser_Create(PermissionRequiredMixin, generic.CreateView):
    permission_required = 'eb_core.advanced'
    form_class = EBUser_Create_Form
    success_url = '/'
    template_name = 'form.html'
