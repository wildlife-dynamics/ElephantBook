from django.core.files.uploadedfile import InMemoryUploadedFile

from .models import *

from io import BytesIO
import numpy as np
import pandas as pd
from PIL import Image
import sys

EXIF_ORIENTATION = {3: 180, 6: 270, 8: 90}


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
    image.convert('RGB').save(b, format='JPEG', quality=50)
    b.seek(0)
    return InMemoryUploadedFile(b, 'ImageField', f'{prefix}_{uploaded_image.name.split(".")[0]}.jpg', 'image/jpeg',
                                sys.getsizeof(b), None)


def get_latest_seek_identities(individuals):
    return [individual.individual_sighting_set.latest('pk').seek_identity for individual in individuals]


def seek_score(given_code, codes, binary=False):
    codes = np.array([np.array(code) for code in codes])

    scores = np.mean(codes == given_code, axis=1) - \
        0.4*np.mean(codes == '?', axis=1)

    # Exclude matches that differ from the given `SEEK_Identity` but don't exclude differences caused by wildcard.
    if binary:
        total_match = ~np.all((codes == given_code) | (codes == '?') | (np.array(given_code) == '?'), axis=1)
        scores[total_match] = np.NAN

    return scores


def score(individual_sighting, individuals=None):
    if individuals is None:
        individuals = Individual.objects.filter(individual_sighting__isnull=False).distinct()

    seek_identities = get_latest_seek_identities(individuals)
    seek_codes = [np.array(seek_identity) for seek_identity in seek_identities]
    seek_scores = seek_score(individual_sighting.seek_identity, seek_codes)

    curvrank_scores = np.zeros_like(seek_scores)

    sum_scores = np.sum([seek_scores, curvrank_scores], axis=0)

    results = pd.DataFrame({
        'individual': individuals,
        'sum_score': sum_scores,
        'seek_score': seek_scores,
        'seek_identity': seek_identities,
        'seek_code': seek_codes,
        'curvrank_score': curvrank_scores,
    }).sort_values('sum_score', ascending=False, ignore_index=True)

    return results
