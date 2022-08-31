import json
import os
from collections import defaultdict

import django.db.models.fields
import numpy as np
import pandas as pd
from django.conf import settings
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    PermissionRequiredMixin,
)
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import IntegrityError
from django.db.models import Max, prefetch_related_objects
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.views import generic
from django_drf_filepond.models import TemporaryUpload
from django_tables2 import SingleTableMixin, SingleTableView
from PIL import Image

from eb_ml.models import Scoring
from eb_ml.tasks import associate_bboxes, detect

from .forms import (
    Combine_Individual_Form,
    EarthRanger_Sighting_Create_Form,
    EBUser_Create_Form,
    Group_Sighting_Notes_Form,
    Group_Sighting_Unphotographed_Individuals_Form,
    Individual_Notes_Form,
    Individual_Profile_Form,
    Individual_Sighting_Form,
    InjuryFormSet,
    Multi_Image_Form,
    Musth_Status_Form,
    Photo_Delete_Form,
    Search_Form,
    Seek_Identity_Form,
    Set_Identity_Form,
    Subgroup_Sighting_Notes_Form,
    subgroup_sighting_formset_constructor,
)
from .models import (
    EarthRanger_Sighting,
    Group_Sighting,
    Individual,
    Individual_Bounding_Box,
    Individual_Photo,
    Individual_Sighting,
    Seek_Identity,
    Sighting_Bounding_Box,
    Sighting_Photo,
    Subgroup_Sighting,
)
from .tables import (
    EarthRanger_Sighting_Table,
    Group_Sighting_Table,
    Individual_Sighting_Table,
    Individual_Table,
    Search_Table,
    Subgroup_Sighting_Table,
)
from .utils import (
    compress_image,
    get_individual_seek_identities,
    score,
    score_seek,
)


class Index_View(LoginRequiredMixin, generic.TemplateView):
    template_name = "index.html"
    extra_context = {"title": "Home"}


class Group_Sighting_List(PermissionRequiredMixin, SingleTableView):
    permission_required = "eb_core.advanced"
    model = Group_Sighting
    ordering = "-datetime"
    template_name = "table.html"
    table_class = Group_Sighting_Table
    table_pagination = False


class Group_Sighting_Create(PermissionRequiredMixin, generic.CreateView):
    permission_required = "eb_core.advanced"
    model = Group_Sighting
    fields = ("lat", "lon", "datetime", "notes")
    template_name = "form.html"

    def get_success_url(self):
        return reverse("group sighting view", kwargs={"pk": self.object.pk})


class Group_Sighting_View(PermissionRequiredMixin, generic.DetailView):
    permission_required = "eb_core.advanced"
    model = Group_Sighting
    template_name = "group_sighting/view.html"

    def dispatch(self, request, *args, **kwargs):
        if type(self) is Group_Sighting_View:
            self.object = self.get_object()
            if isinstance(self.object, EarthRanger_Sighting):
                return redirect("earthranger sighting view", earthranger_serial=self.object.earthranger_serial)

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        prefetch_related_objects(
            [self.object],
            "individual_sighting_set",
            "individual_sighting_set__individual",
            "sighting_photo_set",
            "sighting_photo_set__bounding_box_set",
            "unphotographed_individuals",
            "subgroup_sighting_set",
        )

        images = [
            {
                "id": photo.image.name,
                "url": photo.compressed_image.url,
                "full_res": photo.image.url,
            }
            for photo in self.object.sighting_photo_set.all()
        ]

        boxes = {
            photo.image.name: [
                {
                    "bbox": [bbox.x, bbox.y, bbox.w, bbox.h],
                    "category_id": bbox.individual_sighting_id,
                    "bbox_id": bbox.pk,
                }
                for bbox in photo.bounding_box_set.all()
            ]
            for photo in self.object.sighting_photo_set.all()
        }

        categories = [
            {"id": i, "name": f"Individual Sighting {i}"}
            for i in self.object.individual_sighting_set.values_list("id", flat=True)
        ]

        thumbnails = {"": {i: photo.thumbnail.url for i, photo in enumerate(self.object.sighting_photo_set.all())}}

        context |= {
            # Form for modifying associated `notes`
            "notes_form": Group_Sighting_Notes_Form(instance=self.object),
            # Images associated with the `Group_Sighting` object
            "images": json.dumps(images),
            # JSON bounding boxes for the image viewer
            "boxes": json.dumps(boxes),
            # Annotation categories for all associated `Individual_Sighting` objects
            "categories": json.dumps(categories),
            # Thumbnails associated with the `Group_Sighting` object
            "thumbnails": thumbnails,
            # Form for creating/modifying `Subgroup_Sighting` objects
            "subgroup_sighting_formset": subgroup_sighting_formset_constructor(self.object)(
                queryset=self.object.subgroup_sighting_set.all()
            ),
            # Form for recording unphotographed `Individual` objects
            "unphotographed_individuals_form": Group_Sighting_Unphotographed_Individuals_Form(instance=self.object),
            # Form to delete uploaded photos
            "photo_delete_form": Photo_Delete_Form(photos=self.object.sighting_photo_set.all()),
            # Next `Individual Sighting` id for annotation
            "max_category_id": Individual_Sighting.objects.aggregate(Max("id"))["id__max"] or 0,
        }

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        prefetch_related_objects(
            [self.object],
            "individual_sighting_set",
            "individual_sighting_set__individual",
            "individual_sighting_set__sighting_bounding_box_set",
            "sighting_photo_set",
            "sighting_photo_set__bounding_box_set",
            "unphotographed_individuals",
            "subgroup_sighting_set",
        )

        # Notes
        form = Group_Sighting_Notes_Form(request.POST, instance=self.object)
        if form.is_valid():
            form.save()
        else:
            return HttpResponseRedirect(self.request.path_info)

        # Edit Bounding Boxes
        if request.POST.get("boxes"):
            new_boxes = json.loads(request.POST.get("boxes"))

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
                for box in new_boxes.get(sighting_photo.image.name, []):
                    if "bbox_id" in box:
                        old_box = old_boxes[box["bbox_id"]]
                        old_box.x = box["bbox"][0]
                        old_box.y = box["bbox"][1]
                        old_box.w = box["bbox"][2]
                        old_box.h = box["bbox"][3]
                        old_box.save()
                        del old_boxes[box["bbox_id"]]
                    else:
                        if box["category_id"] not in individual_sightings:
                            individual_sighting = Individual_Sighting(group_sighting=self.object)
                            individual_sighting.save()
                            individual_sightings[box["category_id"]] = individual_sighting

                        individual_sighting = individual_sightings[box["category_id"]]

                        Sighting_Bounding_Box(
                            individual_sighting=individual_sighting,
                            photo=sighting_photo,
                            x=box["bbox"][0],
                            y=box["bbox"][1],
                            w=box["bbox"][2],
                            h=box["bbox"][3],
                        ).save()

            for box in old_boxes.values():
                individual_sighting = box.individual_sighting
                box.delete()
                if not individual_sighting.sighting_bounding_box_set.count():
                    individual_sighting.delete()

            associate_bboxes.delay(list(self.object.sighting_photo_set.values_list("photo_ml", flat=True)))

        # Delete Photos
        form = Photo_Delete_Form(request.POST, photos=self.object.sighting_photo_set.all())
        if form.is_valid():
            form.save()

        # Photos
        for upload_id in request.POST.getlist("filepond"):
            try:
                tu = TemporaryUpload.objects.get(upload_id=upload_id)
            except ObjectDoesNotExist:
                continue
            image = InMemoryUploadedFile(
                tu.file, None, tu.upload_name, Image.open(tu.get_file_path()).get_format_mimetype(), None, None
            )

            instance = Sighting_Photo(
                image=image,
                compressed_image=compress_image(image),
                thumbnail=compress_image(image, maxw=100, prefix="thumbnail"),
                group_sighting=self.object,
            )

            tu.delete()

            upload_to = self.object.get_upload_to()

            instance.name = f"{upload_to}/{instance.image.name}"
            instance.image.field.upload_to = upload_to
            instance.compressed_image.field.upload_to = upload_to
            instance.thumbnail.field.upload_to = upload_to

            try:
                instance.save()
            except IntegrityError as e:
                # Discard photos with duplicate names
                print(instance.name, e)

        detect.delay(list(self.object.sighting_photo_set.values_list("pk", flat=True)))

        # Unphotographed Individuals
        form = Group_Sighting_Unphotographed_Individuals_Form(request.POST, instance=self.object)
        if form.is_valid():
            form.save()

        # Subgroup Sightings
        formset = subgroup_sighting_formset_constructor(self.object)(request.POST)
        for form in formset:
            if form.is_valid():
                instance = form.save(commit=False)
                if "DELETE" in form.cleaned_data and form.cleaned_data["DELETE"]:
                    if instance.pk is not None:
                        instance.delete()
                else:
                    instance.group_sighting = self.object
                    instance.save()
                    form.save_m2m()

        return HttpResponseRedirect(self.request.path_info)


class EarthRanger_Sighting_List(Group_Sighting_List):
    permission_required = "eb_core.main"
    model = EarthRanger_Sighting
    ordering = "-earthranger_serial"
    template_name = "table.html"
    table_class = EarthRanger_Sighting_Table


class EarthRanger_Sighting_Create(PermissionRequiredMixin, generic.CreateView):
    permission_required = "eb_core.main"
    form_class = EarthRanger_Sighting_Create_Form
    model = EarthRanger_Sighting
    template_name = "form.html"

    def get_success_url(self):
        return reverse("earthranger sighting view", kwargs={"earthranger_serial": self.object.earthranger_serial})


class EarthRanger_Sighting_View(Group_Sighting_View):
    permission_required = "eb_core.main"
    model = EarthRanger_Sighting
    template_name = "group_sighting/earthranger_sighting/view.html"

    def get_object(self, **kwargs):
        return EarthRanger_Sighting.objects.get(earthranger_serial=self.kwargs["earthranger_serial"])


class Subgroup_Sighting_List(PermissionRequiredMixin, SingleTableView):
    permission_required = "eb_core.main"
    model = Subgroup_Sighting
    ordering = "-group_sighting__datetime"
    template_name = "table.html"
    table_class = Subgroup_Sighting_Table
    table_pagination = False

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .prefetch_related("group_sighting", "individual_sightings", "unphotographed_individuals")
        )


class Subgroup_Sighting_View(PermissionRequiredMixin, generic.DetailView):
    permission_required = "eb_core.advanced"
    model = Subgroup_Sighting
    template_name = "subgroup_sighting/view.html"

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        prefetch_related_objects(
            [self.object],
            "individual_sightings",
            "individual_sightings__individual",
            "individual_sightings__sighting_bounding_box_set",
            "individual_sightings__sighting_bounding_box_set__photo",
            "unphotographed_individuals",
        )

        bbox_set = [
            bbox
            for individual_sighting in self.object.individual_sightings.all()
            for bbox in individual_sighting.sighting_bounding_box_set.all()
        ]

        images = list(
            {
                bbox.photo.image.name: {
                    "id": bbox.photo.image.name,
                    "url": bbox.photo.compressed_image.url,
                    "full_res": bbox.photo.image.url,
                }
                for bbox in bbox_set
            }.values()
        )

        boxes = defaultdict(list)
        for bbox in bbox_set:
            boxes[bbox.photo.image.name].append(
                {
                    "bbox": [bbox.x, bbox.y, bbox.w, bbox.h],
                    "category_id": bbox.individual_sighting_id,
                    "bbox_id": bbox.pk,
                }
            )

        categories = [
            {"id": i, "name": f"Individual Sighting {i}"}
            for i in self.object.individual_sightings.values_list("id", flat=True)
        ]

        thumbnails = {"": {i: bbox.photo.thumbnail.url for i, bbox in enumerate(bbox_set)}}

        context |= {
            # Form for modifying associated `notes`
            "form": Subgroup_Sighting_Notes_Form(instance=self.object),
            # Images associated with the `Group_Sighting` object
            "images": json.dumps(images),
            # JSON bounding boxes for the image viewer
            "boxes": json.dumps(boxes),
            # Annotation categories for all associated `Individual_Sighting` objects
            "categories": json.dumps(categories),
            # Thumbnails associated with the `Subgroup_Sighting` object
            "thumbnails": thumbnails,
        }

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        form = Subgroup_Sighting_Notes_Form(request.POST, instance=self.object)
        if form.is_valid():
            form.save()

        return HttpResponseRedirect(self.request.path_info)


class Individual_Sighting_List(PermissionRequiredMixin, SingleTableView):
    permission_required = "eb_core.main"
    model = Individual_Sighting
    ordering = "-group_sighting__datetime"
    template_name = "table.html"
    table_class = Individual_Sighting_Table
    table_pagination = False

    def get_queryset(self):
        return super().get_queryset().prefetch_related("group_sighting", "individual")


class Individual_Sighting_Individual_List(Individual_Sighting_List):
    permission_required = "eb_core.main"

    def get_queryset(self):
        return super().get_queryset().filter(individual__pk=self.kwargs["pk"])


class Individual_Sighting_Queue(Individual_Sighting_List):
    permission_required = "eb_core.main"
    ordering = "group_sighting__datetime"

    def get_queryset(self):
        return super().get_queryset().filter(completed=False)


class Individual_Sighting_Expert_Queue(Individual_Sighting_List):
    permission_required = "eb_core.main"
    ordering = "group_sighting__datetime"

    def get_queryset(self):
        return super().get_queryset().filter(completed=True, expert_reviewed=False)


class Individual_Sighting_Unidentified_List(Individual_Sighting_List):
    permission_required = "eb_core.main"
    ordering = "-group_sighting__datetime"

    def get_queryset(self):
        return super().get_queryset().exclude(individual__isnull=False).exclude(unidentifiable=True)


class Individual_Sighting_View(PermissionRequiredMixin, generic.DetailView):
    permission_required = "eb_core.main"
    model = Individual_Sighting
    template_name = "individual_sighting/view.html"

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        prefetch_related_objects(
            [self.object],
            "sighting_bounding_box_set",
            "sighting_bounding_box_set__photo",
            "injury_set",
            "subgroup_sighting_set",
        )

        bbox_set = self.object.sighting_bounding_box_set.all()

        images = [
            {
                "id": bbox.photo.image.name,
                "url": bbox.photo.compressed_image.url,
                "full_res": bbox.photo.image.url,
            }
            for bbox in bbox_set
        ]

        boxes = {
            bbox.photo.image.name: [{"bbox": [bbox.x, bbox.y, bbox.w, bbox.h], "category_id": self.object.pk}]
            for bbox in bbox_set
        }

        thumbnails = {"": {i: bbox.photo.thumbnail.url for i, bbox in enumerate(bbox_set)}}

        context |= {
            # Images associated with the `Individual_Sighting` object
            "images": json.dumps(images),
            # JSON bounding boxes for the image viewer
            "boxes": json.dumps(boxes),
            # Annotation category for the`Individual_Sighting`
            "categories": json.dumps([{"id": self.object.pk, "name": f"Individual Sighting {self.object.pk}"}]),
            # Form for assigning an `Individual` to the `Individual_Sighting` object
            "set_identity_form": Set_Identity_Form(instance=self.object),
            # Form for creating/modifying associated `Injury` objects
            "injury_formset": InjuryFormSet(queryset=self.object.injury_set.all()),
            # Thumbnails associated with the `Individual_Sighting` object
            "thumbnails": thumbnails,
            # Form for modifying various attributes of the `Individual_Sighting` object
            "form": Individual_Sighting_Form(instance=self.object, user=self.request.user),
        }
        # Form for creating/modifying the associated `SEEK_Identity` object
        try:
            context["edit_seek_form"] = Seek_Identity_Form(instance=self.object.seek_identity)
        except ObjectDoesNotExist:
            context["edit_seek_form"] = Seek_Identity_Form()

        # Form for recording `Musth_Status`
        try:
            context["musth_form"] = Musth_Status_Form(instance=self.object.musth_status)
        except ObjectDoesNotExist:
            context["musth_form"] = Musth_Status_Form()

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
                if "DELETE" in form.cleaned_data and form.cleaned_data["DELETE"]:
                    if instance.pk is not None:
                        instance.delete()
                else:
                    instance.individual_sighting = self.object
                    instance.save()

        # Musth_Status
        try:
            form = Musth_Status_Form(request.POST, instance=self.object.musth_status)
        except ObjectDoesNotExist:
            form = Musth_Status_Form(request.POST)

        if form.is_valid():
            instance = form.save(commit=False)
            instance.individual_sighting = self.object
            for field in instance._meta.get_fields():
                if field.name not in ["id", "individual_sighting"] and getattr(instance, field.name):
                    instance.save()
                    break
            else:
                if instance.id:
                    instance.delete()

        # Identity
        form = Set_Identity_Form(request.POST, instance=self.object)
        if form.is_valid():
            form.save()

            # Attribute Propagation
            if self.object.individual and self.object.individual.individual_sighting_set.count() > 1:
                last_individual_sighting = self.object.individual.individual_sighting_set.all().order_by("-pk")[1]

                # Propagate SEEK
                if form.cleaned_data["auto_propagate_seek"]:
                    seek_identity = self.object.seek_identity
                    last_seek_identity = last_individual_sighting.seek_identity
                    for field in Seek_Identity._meta.get_fields():
                        if type(field) == django.db.models.fields.CharField:
                            if getattr(seek_identity, field.name) is None:
                                setattr(seek_identity, field.name, getattr(last_seek_identity, field.name))
                    seek_identity.save()

                # Propagate Injuries
                if form.cleaned_data["auto_propagate_injuries"] and not self.object.injury_set.exists():
                    for injury in last_individual_sighting.injury_set.all():
                        injury.pk = None
                        injury.individual_sighting = self.object
                        injury.save()

        return HttpResponseRedirect(self.request.path_info)


class Individual_List(PermissionRequiredMixin, SingleTableView):
    permission_required = "eb_core.main"
    model = Individual
    ordering = "-pk"
    template_name = "table.html"
    table_class = Individual_Table
    table_pagination = False


class Individual_Create(PermissionRequiredMixin, generic.CreateView):
    permission_required = "eb_core.main"
    model = Individual
    fields = ["name", "notes"]
    template_name = "form.html"

    def get_success_url(self):
        return reverse("individual view", kwargs={"pk": self.object.pk})


class Individual_Combine(PermissionRequiredMixin, generic.FormView):
    permission_required = "eb_core.main"
    form_class = Combine_Individual_Form
    success_url = "."
    template_name = "form.html"

    def form_valid(self, form):
        form.save()
        return super().form_valid(form)


class Individual_View(PermissionRequiredMixin, generic.DetailView):
    permission_required = "eb_core.main"
    model = Individual
    template_name = "individual/view.html"

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        prefetch_related_objects(
            [self.object],
            "individual_sighting_set",
            "individual_photo_set",
            "individual_photo_set__bounding_box_set",
            "individual_sighting_set__sighting_bounding_box_set",
            "individual_sighting_set__sighting_bounding_box_set__photo",
            "individual_sighting_set__group_sighting",
        )

        try:
            last_individual_sighting = self.object.individual_sighting_set.latest()
        except Individual_Sighting.DoesNotExist:
            last_individual_sighting = None

        individual_photo_set = self.object.individual_photo_set.all()
        images = [
            {
                "id": photo.image.name,
                "url": photo.compressed_image.url,
                "full_res": photo.image.url,
            }
            for photo in individual_photo_set
        ]

        boxes = {
            photo.image.name: [
                {
                    "bbox": [bbox.x, bbox.y, bbox.w, bbox.h],
                    "category_id": self.object.pk,
                }
                for bbox in photo.bounding_box_set.all()
            ]
            for photo in individual_photo_set
        }

        thumbnails = {"Individual": {i: photo.thumbnail.url for i, photo in enumerate(individual_photo_set)}}
        image_index = len(thumbnails["Individual"])

        individual_sighting_bbox_set = [
            bbox
            for individual_sighting in self.object.individual_sighting_set.all()
            for bbox in individual_sighting.sighting_bounding_box_set.all()
        ]

        images += [
            {
                "id": bbox.photo.image.name,
                "url": bbox.photo.compressed_image.url,
                "full_res": bbox.photo.image.url,
            }
            for bbox in individual_sighting_bbox_set
        ]

        boxes.update(
            {
                bbox.photo.image.name: [{"bbox": [bbox.x, bbox.y, bbox.w, bbox.h], "category_id": self.object.pk}]
                for bbox in individual_sighting_bbox_set
            }
        )

        for individual_sighting in self.object.individual_sighting_set.all():
            thumbnails[individual_sighting.group_sighting.pk] = {
                i + image_index: bbox.photo.thumbnail.url
                for i, bbox in enumerate(individual_sighting.sighting_bounding_box_set.all())
            }
            image_index += len(thumbnails[individual_sighting.group_sighting.pk])

        context |= {
            # Latest `Individual_Sighting` associated with the `Individual` object
            "last_individual_sighting": last_individual_sighting,
            # Form for creating `Individual_Photo` objects
            "form": Multi_Image_Form(),
            # Form for modifying associated `notes`
            "notes_form": Individual_Notes_Form(instance=self.object),
            # Images associated with the `Individual` object
            "images": json.dumps(images),
            # JSON boudning boxes for the image viewer
            "boxes": json.dumps(boxes),
            # Annotation category for the (single) `Individual`
            "categories": json.dumps([{"id": self.object.pk, "name": f"{self.object.name}"}]),
            # Thumbnails associated with the `Individual_Sighting` object
            "thumbnails": thumbnails,
            # Form to set the `profile` attribute of the `Individual`
            "profile_form": Individual_Profile_Form(self.object),
        }

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Edit Bounding Boxes
        if request.POST.get("boxes"):
            boxes = json.loads(request.POST.get("boxes"))

            self.object.individual_bounding_box_set.all().delete()

            for individual_photo in self.object.individual_photo_set.all():
                for box in boxes[individual_photo.image.name]:
                    Individual_Bounding_Box(
                        individual=self.object,
                        photo=individual_photo,
                        x=box["bbox"][0],
                        y=box["bbox"][1],
                        w=box["bbox"][2],
                        h=box["bbox"][3],
                    ).save()

        # Photos
        for upload_id in request.POST.getlist("filepond"):
            tu = TemporaryUpload.objects.get(upload_id=upload_id)
            image = InMemoryUploadedFile(
                tu.file, None, tu.upload_name, Image.open(tu.get_file_path()).get_format_mimetype(), None, None
            )

            instance = Individual_Photo(
                image=image,
                compressed_image=compress_image(image),
                thumbnail=compress_image(image, maxw=100, prefix="thumbnail"),
                individual=self.object,
            )

            tu.delete()

            upload_to = f"individual/{self.object.pk}"
            instance.name = f"{upload_to}/{instance.image.name}"
            instance.image.field.upload_to = upload_to
            instance.compressed_image.field.upload_to = upload_to
            instance.thumbnail.field.upload_to = upload_to
            try:
                instance.save()
            except IntegrityError as e:
                # Discard photos with duplicate names
                print(instance.name, e)

        # Profile
        form = Individual_Profile_Form(self.object, request.POST)
        if form.is_valid():
            form.save(self.object)

        # Notes
        form = Individual_Notes_Form(request.POST, instance=self.object)
        if form.is_valid():
            form.save()

        return HttpResponseRedirect(self.request.path_info)


class Search_View(PermissionRequiredMixin, SingleTableMixin, generic.TemplateView):
    permission_required = "eb_core.main"
    template_name = "search/view.html"

    table_class = Search_Table
    table_pagination = False

    def get_table_data(self):

        individuals = Individual.objects.filter(individual_sighting__isnull=False).distinct()

        if self.request.GET.get("region"):
            individuals = individuals.filter(
                individual_sighting__group_sighting__json__event_details__RegionName=self.request.GET["region"]
            )

        individuals, seek_identities = get_individual_seek_identities(individuals)

        if individuals.exists():
            seek_scores = score_seek(
                Seek_Identity_Form(self.request.GET).save(commit=False),
                [np.array(seek_identity) for seek_identity in seek_identities],
                binary="binary" in self.request.GET and self.request.GET["binary"] == "on",
            )

            df = pd.DataFrame(
                {
                    "individual": individuals,
                    "seek_code": [str(seek_identity) for seek_identity in seek_identities],
                    "score": seek_scores,
                    "seek_score": seek_scores,
                },
                index=individuals.values_list("pk", flat=True),
            ).dropna()

            try:
                scoring_df = pd.DataFrame(
                    Scoring.objects.get(individual_sighting_id=self.request.GET["individual_sighting"]).data
                )
                scoring_df.set_index(scoring_df.pop("individual").values, inplace=True)
                df = df[["individual", "seek_score"]].join(scoring_df.drop(columns="seek_score"))
            except (KeyError, ObjectDoesNotExist):
                pass

            df = df.sort_values("score", ascending=False, ignore_index=True)
            df["rank"] = df.index + 1

        return df.to_dict("records")

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        context["form"] = Search_Form(self.request.GET)

        return context


class Match_View(PermissionRequiredMixin, generic.DetailView):
    permission_required = "eb_core.main"
    model = Individual_Sighting
    template_name = "search/view.html"

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        results = score(self.object)

        context |= {
            "results": results,
        }

        return context


class Stats_View(PermissionRequiredMixin, generic.TemplateView):
    permission_required = "eb_core.advanced"
    template_name = "stats/index.html"

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        context |= {
            "num_group_sightings": Group_Sighting.objects.count(),
            "num_individuals": Individual.objects.count(),
            "num_individual_sightings": Individual_Sighting.objects.count(),
            "num_sighting_photos": Sighting_Photo.objects.count(),
            "num_sighting_bounding_boxes": Sighting_Bounding_Box.objects.count(),
        }

        return context


class Media_View(LoginRequiredMixin, generic.TemplateView):
    template_name = "view_media/index.html"

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)

        context |= {
            "url": os.path.join(settings.MEDIA_URL, kwargs["name"]),
        }

        return context


class EBUser_Create(PermissionRequiredMixin, generic.CreateView):
    permission_required = "eb_core.advanced"
    form_class = EBUser_Create_Form
    success_url = "/"
    template_name = "form.html"
