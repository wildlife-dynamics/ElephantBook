import json

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.db.models import Q, prefetch_related_objects
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import generic
from django_tables2 import SingleTableView

from eb_anno.tables import Assignment_Table
from eb_core.forms import Elephant_Voices_Identity_Form, Seek_Identity_Form

from .forms import Assignment_Form
from .models import Assignment, Assignment_Bounding_Box


class Assignment_List(PermissionRequiredMixin, SingleTableView):
    permission_required = "eb_anno.advanced"
    model = Assignment
    ordering = "pk"
    template_name = "table.html"
    table_class = Assignment_Table
    table_pagination = False

    def get_queryset(self):
        return super().get_queryset().select_related("annotation_target").prefetch_related("users")


class Assignment_Queue(Assignment_List):
    permission_required = "eb_anno.advanced"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(Q(completed=False) & (Q(users=self.request.user) | Q(users=None)))
        return queryset


class Assignment_Completed_List(Assignment_List):
    permission_required = "eb_anno.main"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(Q(completed=True) & (Q(users=self.request.user) | Q(users=None)))
        return queryset


class Assignment_Needs_Review_List(Assignment_List):
    permission_required = "eb_anno.main"

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.filter(needs_review=True)
        return queryset


class Assignment_Get(PermissionRequiredMixin, generic.RedirectView):
    permission_required = "eb_anno.main"

    def get_redirect_url(self, *args, **kwargs):
        completed_targets = Assignment.objects.filter(users=self.request.user, completed=True).values_list(
            "annotation_target", flat=True
        )
        try:
            assignment = (
                Assignment.objects.filter(Q(users=self.request.user) | Q(users=None), completed=False)
                .exclude(annotation_target__in=completed_targets)
                .latest("annotation_target__datetime")
            )
        except Assignment.DoesNotExist:
            return reverse("index")

        assignment.users.clear()
        assignment.users.add(self.request.user)

        return reverse("eb_anno:assignment view", kwargs={"pk": assignment.pk})


class Assignment_View(PermissionRequiredMixin, generic.DetailView):
    permission_required = "eb_anno.main"
    model = Assignment
    template_name = "eb_anno/assignment/view.html"

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        prefetch_related_objects(
            [self.object],
            "annotation_target__annotation_target_photo_set",
            "annotation_target__annotation_target_photo_set__bounding_box_set",
        )

        images = [
            {
                "id": photo.image.name,
                "url": photo.compressed_image.url,
                "full_res": photo.image.url,
            }
            for photo in self.object.annotation_target.annotation_target_photo_set.all()
        ]

        boxes = {
            photo.image.name: [
                {
                    "bbox": [bbox.x, bbox.y, bbox.w, bbox.h],
                    "category_id": self.object.pk,
                    "bbox_id": bbox.pk,
                }
                for bbox in photo.bounding_box_set.filter(assignment_bounding_box__assignment=self.object)
            ]
            for photo in self.object.annotation_target.annotation_target_photo_set.all()
        }

        thumbnails = {
            "": {
                i: photo.thumbnail.url
                for i, photo in enumerate(self.object.annotation_target.annotation_target_photo_set.all())
            }
        }

        context |= {
            # Images associated with the `Annotation Target` object
            "images": json.dumps(images),
            # JSON bounding boxes for the image viewer
            "boxes": json.dumps(boxes),
            # Annotation category for the`Individual_Sighting`
            "categories": json.dumps([{"id": self.object.pk, "name": f"Assignment {self.object.pk}"}]),
            # Thumbnails associated with the `Individual_Sighting` object
            "thumbnails": thumbnails,
            # Form for setting the `completed` status of the `Assignment` object
            "form": Assignment_Form(instance=self.object),
            # Disallow "Add Elephant to List of Identities" button
            "fixed_categories": True,
        }
        if self.object.seek_identity is not None:
            context["seek_identity_form"] = Seek_Identity_Form(instance=self.object.seek_identity)

        if self.object.elephant_voices_identity is not None:
            context["elephant_voices_identity_form"] = Elephant_Voices_Identity_Form(
                instance=self.object.elephant_voices_identity
            )

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Edit Bounding Boxes
        if request.POST.get("boxes"):
            new_boxes = json.loads(request.POST.get("boxes"))

            old_boxes = {bbox.pk: bbox for bbox in self.object.assignment_bounding_box_set.all()}

            for annotation_target_photo in self.object.annotation_target.annotation_target_photo_set.all():
                for box in new_boxes.get(annotation_target_photo.image.name, []):
                    if "bbox_id" in box and box["bbox_id"] in old_boxes:
                        old_box = old_boxes[box["bbox_id"]]
                        old_box.x = box["bbox"][0]
                        old_box.y = box["bbox"][1]
                        old_box.w = box["bbox"][2]
                        old_box.h = box["bbox"][3]
                        old_box.save()
                        del old_boxes[box["bbox_id"]]
                    else:
                        Assignment_Bounding_Box(
                            assignment=self.object,
                            photo=annotation_target_photo,
                            x=box["bbox"][0],
                            y=box["bbox"][1],
                            w=box["bbox"][2],
                            h=box["bbox"][3],
                        ).save()

            for box in old_boxes.values():
                box.delete()

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
