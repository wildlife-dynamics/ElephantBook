from django.core.exceptions import ObjectDoesNotExist
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import IntegrityError
import django.db.models.fields
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render, redirect

from .forms import *
from .models import *

from io import BytesIO
import json
import numpy as np
from PIL import Image
import sys

EXIF_ORIENTATION = {3: 180, 6: 270, 8: 90}


def index(request):
    """View function for welcome page of site."""
    context = {}
    return render(request, 'index.html', context)


def add_earthranger(request):
    """View function for creating `Group_Sighting` objects from EarthRanger events."""
    if request.method == 'POST':
        form = Add_Group_Sighting_Form(request.POST)
        if form.is_valid():
            instance = form.save()
            request.method = 'GET'
            return redirect(group_sighting_view, earthranger_serial=instance.earthranger_serial)
        else:
            print(f'Invalid: {form.errors}')
            return HttpResponseBadRequest('Failed to create Group_Sighting.')
    else:
        context = {'form': Add_Group_Sighting_Form()}

        return render(request, 'add_earthranger/index.html', context)


def group_sighting_list(request):
    """View function to list `Group_Sighting` objects."""
    group_sightings = Group_Sighting.objects.order_by('-datetime')
    context = {'group_sightings': group_sightings}
    return render(request, 'group_sighting/index.html', context)


def group_sighting_view(request, earthranger_serial):
    """View function to view a `Group_Sighting` object."""
    group_sighting = get_object_or_404(Group_Sighting, earthranger_serial=earthranger_serial)
    group_sighting_photo_set = group_sighting.sighting_photo_set.all()

    images = [{
        'id': photo.image.name,
        'url': photo.compressed_image.url,
        'full_res': photo.image.url
    } for photo in group_sighting_photo_set]
    image_index_map = dict(zip([image['id'] for image in images], range(len(images))))

    individual_sighting_categories = {k: k.id for i, k in enumerate(group_sighting.individual_sighting_set.all(), 1)}

    boxes = {
        photo.image.name: [{
            'bbox': [bbox.x, bbox.y, bbox.w, bbox.h],
            'category_id': individual_sighting_categories[bbox.individual_sighting],
            'bbox_id': bbox.id,
        } for bbox in photo.sighting_bounding_box_set.all()]
        for photo in group_sighting_photo_set
    }

    categories = [{'id': i, 'name': f'Individual Sighting {i}'} for i in individual_sighting_categories.values()]

    thumbnails = {
        group_sighting.earthranger_serial:
        {image_index_map[image.image.name]: image.thumbnail.url
         for image in group_sighting_photo_set}
    }

    context = {
        # Selected `Group_Sighting`
        'group_sighting': group_sighting,
        # Form for creating `Sighting_Photo` objects
        'form': Multi_Image_Form(),
        # Form for modifying associated `notes`
        'notes_form': Group_Sighting_Notes_Form(instance=group_sighting),
        # Images associated with the `Group_Sighting` object
        'images': json.dumps(images),
        # JSON bounding boxes for the image viewer
        'boxes': json.dumps(boxes),
        # Annotation categories for all associated `Individual_Sighting` objects
        'categories': json.dumps(categories),
        # Thumbnails associated with the `Group_Sighting` object
        'thumbnails': thumbnails,
    }
    return render(request, 'group_sighting/view.html', context)


def compress_image(uploaded_image, maxw=1000, prefix='compressed'):
    """Utility function to resize an image to specified maximum dimension and apply a 50% JPEG compression.

    Parameters
    ----------
    uploaded_image: django.core.files.uploadedfile.InMemoryUploadedFile
        Full size image to crop.
    maxw: int
        Maximum dimension of output image.

    Returns
    -------
    django.core.files.uploadedfile.InMemoryUploadedFile
        Resized and JPEG-compressed version of `uploaded_image`.
    """
    image = Image.open(uploaded_image)

    # Compression doesn't preserve EXIF
    if image._exif is not None and 274 in image._exif and image._exif[274] in EXIF_ORIENTATION:
        image = image.rotate(EXIF_ORIENTATION[image._exif[274]], expand=True)

    image.thumbnail([maxw, maxw])
    b = BytesIO()
    image.save(b, format='JPEG', quality=50)
    b.seek(0)
    return InMemoryUploadedFile(b, 'ImageField', f'{prefix}_{uploaded_image.name.split(".")[0]}.jpg', 'image/jpeg',
                                sys.getsizeof(b), None)


def group_sighting_edit(request, earthranger_serial):
    """View function to modify a `Group_Sighting` object."""
    group_sighting = get_object_or_404(Group_Sighting, earthranger_serial=earthranger_serial)

    if request.method == 'POST':
        # Edit Bounding Boxes
        if request.POST.get('boxes'):
            new_boxes = json.loads(request.POST.get('boxes'))

            individual_sightings = {
                individual_sighting.id: individual_sighting
                for individual_sighting in group_sighting.individual_sighting_set.all()
            }
            old_boxes = {
                bbox.id: bbox
                for individual_sighting in group_sighting.individual_sighting_set.all()
                for bbox in individual_sighting.sighting_bounding_box_set.all()
            }

            for sighting_photo in group_sighting.sighting_photo_set.all():
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
                            individual_sighting = Individual_Sighting(group_sighting=group_sighting)
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
                                          group_sighting=group_sighting)
                instance.image_name = f'earthranger/{earthranger_serial}/{instance.image.name}'
                instance.image.field.upload_to = f'earthranger/{earthranger_serial}'
                instance.compressed_image.field.upload_to = f'earthranger/{earthranger_serial}'
                instance.thumbnail.field.upload_to = f'earthranger/{earthranger_serial}'
                try:
                    instance.save()
                except IntegrityError as e:
                    # Discard photos with duplicate names
                    print(instance.image_name, e)
                    continue

        # Notes
        form = Group_Sighting_Notes_Form(request.POST, instance=group_sighting)
        if form.is_valid():
            form.save()

    return redirect(group_sighting_view, earthranger_serial=earthranger_serial)


def individual_sighting_list(request, individual_id=None):
    """View function to list `Individual_Sighting` objects."""
    if individual_id is not None:
        individual_sightings = get_object_or_404(Individual, pk=individual_id).individual_sighting_set.all().reverse()
    else:
        individual_sightings = Individual_Sighting.objects.order_by('pk').reverse()
    context = {'individual_sightings': individual_sightings}
    return render(request, 'individual_sighting/index.html', context)


def individual_sighting_queue(request):
    """View function to list `Individual_Sighting` objects that are not marked `completed`."""
    individual_sightings = Individual_Sighting.objects.filter(completed=False)
    context = {'individual_sightings': individual_sightings}
    return render(request, 'individual_sighting/queue.html', context)


def individual_sighting_expert_queue(request):
    """View function to list `Individual_Sighting` objects that are marked `completed` and not marked `expert_reviewed`."""
    individual_sightings = Individual_Sighting.objects.filter(completed=True, expert_reviewed=False)
    context = {'individual_sightings': individual_sightings}
    return render(request, 'individual_sighting/expert_queue.html', context)


def individual_sighting_unidentified(request):
    """View function to list `Individual_Sighting` objects that have not been assigned an `Individual`."""
    individual_sightings = Individual_Sighting.objects.all().exclude(individual__isnull=False)
    context = {'individual_sightings': individual_sightings}
    return render(request, 'individual_sighting/unidentified.html', context)


def individual_sighting_view(request, individual_sighting_id):
    """View function to view an `Individual_Sighting` object."""
    individual_sighting = get_object_or_404(Individual_Sighting, pk=individual_sighting_id)

    bbox_set = individual_sighting.sighting_bounding_box_set.all()

    images = [{
        'id': bbox.photo.image.name,
        'url': bbox.photo.compressed_image.url,
        'full_res': bbox.photo.image.url
    } for bbox in bbox_set]
    image_index_map = dict(zip([image['id'] for image in images], range(len(images))))

    boxes = {
        bbox.photo.image.name: [{
            'bbox': [bbox.x, bbox.y, bbox.w, bbox.h],
            'category_id': individual_sighting.id
        }]
        for bbox in bbox_set
    }

    expert_reviewed_form = Expert_Reviewed_Form(instance=individual_sighting)
    expert_reviewed_form.fields['expert_reviewed'].disabled = not request.user.expert

    thumbnails = {
        individual_sighting.group_sighting.earthranger_serial:
        {image_index_map[image.image.name]: image.thumbnail.url
         for image in [bbox.photo for bbox in bbox_set]}
    }

    context = {
        # Selected `Individual_Sighting`
        'individual_sighting': individual_sighting,
        # Images associated with the `Individual_Sighting` object
        'images': json.dumps(images),
        # JSON bounding boxes for the image viewer
        'boxes': json.dumps(boxes),
        # Annotation category for the`Individual_Sighting`
        'categories': json.dumps([{
            'id': individual_sighting.id,
            'name': f'Individual Sighting {individual_sighting.id}'
        }]),
        # Form for assigning an `Individual` to the `Individual_Sighting` object
        'set_identity_form': Set_Identity_Form(instance=individual_sighting),
        # Form for assigning the `completed` status
        'completed_annotation_form': Completed_Annotation_Form(instance=individual_sighting),
        # Form for assigning the `expert_reviewed` status
        'expert_reviewed_form': expert_reviewed_form,
        # Form for modifying associated `notes`
        'notes_form': Individual_Sighting_Notes_Form(instance=individual_sighting),
        # Form for creating/modifying associated `Injury` objects
        'injury_formset': InjuryFormSet(queryset=individual_sighting.injury_set.all()),
        # Thumbnails associated with the `Individual_Sighting` object
        'thumbnails': thumbnails,
    }
    # Form for creating/modifying the associated `SEEK_Identity` object
    try:
        context['edit_seek_form'] = Seek_Identity_Form(instance=individual_sighting.seek_identity)
    except ObjectDoesNotExist:
        context['edit_seek_form'] = Seek_Identity_Form()

    # Form for creating/modifying the associated `Elephant_Voices_Identity` object
    try:
        context['elephant_voices_identity_form'] = Elephant_Voices_Identity_Form(
            instance=individual_sighting.elephant_voices_identity)
    except ObjectDoesNotExist:
        context['elephant_voices_identity_form'] = Elephant_Voices_Identity_Form()

    return render(request, 'individual_sighting/view.html', context)


def individual_sighting_edit(request, individual_sighting_id):
    """View function to modify an `Individual_Sighting` object."""
    individual_sighting = get_object_or_404(Individual_Sighting, pk=individual_sighting_id)

    if request.method == 'POST':
        # SEEK
        try:
            form = Seek_Identity_Form(request.POST, instance=individual_sighting.seek_identity)
        except ObjectDoesNotExist:
            form = Seek_Identity_Form(request.POST)

        if form.is_valid():
            form.save(individual_sighting)

        # Elephant Voices
        try:
            form = Elephant_Voices_Identity_Form(request.POST, instance=individual_sighting.elephant_voices_identity)
        except ObjectDoesNotExist:
            form = Elephant_Voices_Identity_Form(request.POST)

        if form.is_valid():
            form.save(individual_sighting)

        # Completed Annotation
        form = Completed_Annotation_Form(request.POST, instance=individual_sighting)
        if form.is_valid():
            form.save()

        # Expert-Reviewed
        form = Expert_Reviewed_Form(request.POST, instance=individual_sighting)
        if form.is_valid():
            form.save()

        # Notes
        form = Individual_Sighting_Notes_Form(request.POST, instance=individual_sighting)
        if form.is_valid():
            form.save()

        # Injuries
        formset = InjuryFormSet(request.POST)
        for form in formset:
            if form.is_valid():
                instance = form.save(commit=False)
                if 'DELETE' in form.cleaned_data and form.cleaned_data['DELETE']:
                    instance.delete()
                else:
                    instance.individual_sighting = individual_sighting
                    instance.save()

        # Identity
        form = Set_Identity_Form(request.POST, instance=individual_sighting)
        if form.is_valid():
            form.save()
            if individual_sighting.individual.individual_sighting_set.count() > 1:
                last_individual_sighting = individual_sighting.individual.individual_sighting_set.all().order_by(
                    '-pk')[1]

                # Propagate SEEK
                if form.cleaned_data['auto_propagate_seek']:
                    seek_identity = individual_sighting.seek_identity
                    last_seek_identity = last_individual_sighting.seek_identity
                    for field in Seek_Identity._meta.get_fields():
                        if type(field) == django.db.models.fields.CharField:
                            if getattr(seek_identity, field.name) is None:
                                setattr(seek_identity, field.name, getattr(last_seek_identity, field.name))
                    seek_identity.save()

                # Propagate Injuries
                if form.cleaned_data['auto_propagate_injuries'] and not individual_sighting.injury_set.exists():
                    for injury in last_individual_sighting.injury_set.all():
                        injury.pk = None
                        injury.individual_sighting = individual_sighting
                        injury.save()

    return redirect(individual_sighting_view, individual_sighting_id=individual_sighting_id)


def individual_list(request):
    """View function to list `Individual` objects."""
    individuals = Individual.objects.all()

    context = {
        # Set of time-sorted individuals
        'individuals': individuals,
        # Form for creating a new `Individual` object from a given name
        'add_form': Add_Individual_Form(),
        # Form for combining two `Individual` objects
        'combine_form': Combine_Individual_Form(),
    }
    return render(request, 'individual/index.html', context)


def individual_add(request):
    """View function for creating `Individual` objects."""
    if request.method == 'POST':
        form = Add_Individual_Form(request.POST)
        if form.is_valid():
            form.save()

    return redirect(individual_list)


def individual_combine(request):
    """View function for combining `Individual` objects."""
    if request.method == 'POST':
        form = Combine_Individual_Form(request.POST)
        if form.is_valid():
            assert form.data['individual_1'] != form.data['individual_2']
            individual_1 = get_object_or_404(Individual, pk=form.data['individual_1'])
            individual_2 = get_object_or_404(Individual, pk=form.data['individual_2'])
            for individual_sighting in individual_2.individual_sighting_set.all():
                individual_sighting.individual = individual_1
                individual_sighting.save()

            individual_1.notes += f'\nAutomatically copied notes from Individual {individual_2.id}: ' + individual_2.notes
            for individual_photo in individual_2.individual_photo_set.all():
                individual_photo.individual = individual_1
                individual_photo.save()

            individual_1.save()
            individual_2.delete()
    return redirect(individual_list)


def individual_view(request, individual_id):
    """View function to view an `Individual` object."""
    individual = get_object_or_404(Individual, pk=individual_id)
    try:
        last_individual_sighting = individual.individual_sighting_set.latest()
    except Individual_Sighting.DoesNotExist:
        last_individual_sighting = None

    individual_photo_set = individual.individual_photo_set.all()
    images = [{
        'id': photo.image.name,
        'url': photo.compressed_image.url,
        'full_res': photo.image.url
    } for photo in individual_photo_set]

    boxes = {
        photo.image.name: [{
            'bbox': [bbox.x, bbox.y, bbox.w, bbox.h],
            'category_id': individual.id,
        } for bbox in photo.individual_bounding_box_set.all()]
        for photo in individual_photo_set
    }

    image_index_map = dict(zip([image['id'] for image in images], range(len(images))))
    thumbnails = {
        'Individual': {image_index_map[photo.image.name]: photo.thumbnail.url
                       for photo in individual_photo_set}
    }

    individual_sighting_bbox_set = [
        bbox for individual_sighting in individual.individual_sighting_set.all()
        for bbox in individual_sighting.sighting_bounding_box_set.all()
    ]

    images += [{
        'id': bbox.photo.image.name,
        'url': bbox.photo.compressed_image.url,
        'full_res': bbox.photo.image.url
    } for bbox in individual_sighting_bbox_set]

    boxes.update({
        bbox.photo.image.name: [{
            'bbox': [bbox.x, bbox.y, bbox.w, bbox.h],
            'category_id': individual.id
        }]
        for bbox in individual_sighting_bbox_set
    })

    image_index = len(image_index_map)
    for individual_sighting in individual.individual_sighting_set.all():
        thumbnails[individual_sighting.group_sighting.earthranger_serial] = {
            i + image_index: bbox.photo.thumbnail.url
            for i, bbox in enumerate(individual_sighting.sighting_bounding_box_set.all())
        }
        image_index += len(thumbnails[individual_sighting.group_sighting.earthranger_serial])

    context = {
        # Selected `Individual`
        'individual': individual,
        # Latest `Individual_Sighting` associated with the `Individual` object
        'last_individual_sighting': last_individual_sighting,
        # Form for creating `Individual_Photo` objects
        'form': Multi_Image_Form(),
        # Form for modifying associated `notes`
        'notes_form': Individual_Notes_Form(instance=individual),
        # Images associated with the `Individual` object
        'images': json.dumps(images),
        # JSON boudning boxes for the image viewer
        'boxes': json.dumps(boxes),
        # Annotation category for the (single) `Individual`
        'categories': json.dumps([{
            'id': individual.id,
            'name': f'{individual.name}'
        }]),
        # Thumbnails associated with the `Individual_Sighting` object
        'thumbnails': thumbnails,
        # Form to set the `profile` attribute of the `Individual`
        'profile_form': Individual_Profile_Form(individual),
    }
    return render(request, 'individual/view.html', context)


def individual_edit(request, individual_id):
    """View function to modify an `Individual` object."""
    individual = get_object_or_404(Individual, pk=individual_id)

    if request.method == 'POST':
        # Edit Bounding Boxes
        if request.POST.get('boxes'):
            boxes = json.loads(request.POST.get('boxes'))

            individual.individual_bounding_box_set.all().delete()

            for individual_photo in individual.individual_photo_set.all():
                for box in boxes[individual_photo.image.name]:
                    Individual_Bounding_Box(individual=individual,
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
                                            individual=individual)
                instance.image_name = f'individual/{individual_id}/{instance.image.name}'
                instance.image.field.upload_to = f'individual/{individual_id}'
                instance.compressed_image.field.upload_to = f'individual/{individual_id}'
                instance.thumbnail.field.upload_to = f'individual/{individual_id}'
                try:
                    instance.save()
                except IntegrityError as e:
                    # Discard photos with duplicate names
                    print(instance.image_name, e)
                    continue

        # Profile
        form = Individual_Profile_Form(individual, request.POST,)
        if form.is_valid():
            if 'individual_photo' in form.cleaned_data['photos']:
                individual.profile_type = ContentType.objects.get_for_model(Individual_Photo)
                individual.profile_id = form.cleaned_data['photos'].split(' ')[-1]
            elif 'sighting_photo' in form.cleaned_data['photos']:
                individual.profile_type = ContentType.objects.get_for_model(Sighting_Photo)
                individual.profile_id = form.cleaned_data['photos'].split(' ')[-1]
            else:
                individual.profile_type = None
                individual.profile_id = None

            individual.save()

        # Notes
        form = Individual_Notes_Form(request.POST, instance=individual)
        if form.is_valid():
            form.save()

    return redirect(individual_view, individual_id=individual_id)


def search(request):
    """View function to list `Individual_Sighting` objects by similarity to given `Individual_Sighting`."""
    given_code = Seek_Identity_Form(request.GET).save(commit=False)

    seek_identities = np.array(Seek_Identity.objects.all(), dtype=object)
    if seek_identities is None:
        return redirect(index)

    codes = np.array([np.array(code) for code in seek_identities])

    # Exclude matches that differ from the given `SEEK_Identity` but don't exclude differences caused by wildcard.
    if 'binary' in request.GET and request.GET['binary'] == 'on':
        total_match = np.all((codes == given_code) | (codes == '?') | (np.array(given_code) == '?'), axis=1)
        seek_identities = seek_identities[total_match]
        codes = codes[total_match]

    # Exclude matches from other `Individual` objects.
    if 'individual' in request.GET:
        total_match = np.array([
            seek_identity.individual_sighting.individual is not None
            and seek_identity.individual_sighting.individual.pk == int(request.GET['individual'])
            for seek_identity in seek_identities
        ])
        seek_identities = seek_identities[total_match]
        codes = codes[total_match]

    scores = np.mean(codes == given_code, axis=1) - \
        0.4*np.mean(codes == '?', axis=1)

    results = np.column_stack((scores, seek_identities))[np.argsort(-scores)]

    context = {
        'form': Search_Form(instance=Search_Form(request.GET).save(commit=False)),
        'results': results,
    }
    return render(request, 'search/index.html', context)


def stats(request):
    """View function to provide basic database stats."""
    context = {
        'num_group_sightings': Group_Sighting.objects.count(),
        'num_individuals': Individual.objects.count(),
        'num_individual_sightings': Individual_Sighting.objects.count(),
        'num_sighting_photos': Sighting_Photo.objects.count(),
        'num_sighting_bounding_boxes': Sighting_Bounding_Box.objects.count(),
    }
    return render(request, 'stats/index.html', context)
