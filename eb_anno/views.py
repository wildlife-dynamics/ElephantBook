from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import generic

import json

from .forms import *
from .models import *


class Assignment_List(PermissionRequiredMixin, generic.ListView):
    permission_required = 'eb_anno.advanced'
    model = Assignment
    ordering = 'pk'
    paginate_by = 100
    template_name = 'eb_anno/assignment/list.html'


class Assignment_Queue(Assignment_List):
    permission_required = 'eb_anno.main'

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(Q(completed=False) & (Q(users__in=[self.request.user]) | Q(users=None)))
        return queryset


class Assignment_Completed_List(Assignment_List):
    permission_required = 'eb_anno.main'

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(Q(completed=True) & (Q(users__in=[self.request.user]) | Q(users=None)))
        return queryset


class Assignment_Needs_Review_List(Assignment_List):
    permission_required = 'eb_anno.main'

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(needs_review=True)
        return queryset


class Assignment_View(PermissionRequiredMixin, generic.DetailView):
    permission_required = 'eb_anno.main'
    model = Assignment
    template_name = 'eb_anno/assignment/view.html'

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        annotation_target_photo_set = self.object.annotation_target.annotation_target_photo_set.all()

        images = [{
            'id': photo.image.name,
            'url': photo.compressed_image.url,
            'full_res': reverse('view media', args=(photo.image.name, )),
        } for photo in annotation_target_photo_set]

        boxes = {
            photo.image.name: [{
                'bbox': [bbox.x, bbox.y, bbox.w, bbox.h],
                'category_id': self.object.pk,
                'bbox_id': bbox.pk,
            } for bbox in photo.bounding_box_set.filter(assignment_bounding_box__assignment=self.object)]
            for photo in annotation_target_photo_set
        }

        thumbnails = {
            '':
            {i: Annotation_Target_Photo.objects.get(image=image['id']).thumbnail.url
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
                'name': f'Assignment {self.object.pk}'
            }]),
            # Thumbnails associated with the `Individual_Sighting` object
            'thumbnails': thumbnails,
            # Form for setting the `completed` status of the `Assignment` object
            'form': Assignment_Form(instance=self.object),
            # Disallow "Add Elephant to List of Identities" button
            'fixed_categories': True,
        }
        if self.object.seek_identity is not None:
            context['seek_identity_form'] = Seek_Identity_Form(instance=self.object.seek_identity)

        if self.object.elephant_voices_identity is not None:
            context['elephant_voices_identity_form'] = Elephant_Voices_Identity_Form(
                instance=self.object.elephant_voices_identity)

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Edit Bounding Boxes
        if request.POST.get('boxes'):
            boxes = json.loads(request.POST.get('boxes'))

            self.object.assignment_bounding_box_set.all().delete()

            for annotation_target_photo in self.object.annotation_target.annotation_target_photo_set.all():
                for box in boxes[annotation_target_photo.image.name]:
                    Assignment_Bounding_Box(assignment=self.object,
                                            photo=annotation_target_photo,
                                            x=box['bbox'][0],
                                            y=box['bbox'][1],
                                            w=box['bbox'][2],
                                            h=box['bbox'][3]).save()

        # SEEK
        if self.object.seek_identity is not None:
            form = Seek_Identity_Form(request.POST, instance=self.object.seek_identity)
            if form.is_valid():
                form.save()

        # Elephant Voices
        if self.object.elephant_voices_identity is not None:
            form = Elephant_Voices_Identity_Form(request.POST, instance=self.object.elephant_voices_identity)
            if form.is_valid():
                form.save()

        # Various `Assignment` attributes
        form = Assignment_Form(request.POST, instance=self.object)
        if form.is_valid():
            form.save()

        return HttpResponseRedirect(self.request.path_info)
