import sys
from io import BytesIO

import numpy as np
import pandas as pd
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db.models import OuterRef, Subquery
from PIL import Image

from .models import Individual, Individual_Sighting, Seek_Identity

EXIF_ORIENTATION = {3: 180, 6: 270, 8: 90}


def compress_image(uploaded_image, maxw=1000, prefix="compressed"):
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
    image.convert("RGB").save(b, format="JPEG", quality=50)
    b.seek(0)
    return InMemoryUploadedFile(
        b, "ImageField", f'{prefix}_{uploaded_image.name.split(".")[0]}.jpg', "image/jpeg", sys.getsizeof(b), None
    )


def score_seek(out_code, database_codes, binary=False):
    out_code = np.array(out_code)
    database_codes = np.array([np.array(code) for code in database_codes])

    scores = np.mean(database_codes == out_code, axis=1) - 0.4 * np.mean(database_codes == "?", axis=1)

    # Exclude matches that differ from the given `SEEK_Identity` but don't exclude differences caused by wildcard.
    if binary:
        scores[
            ~np.all((database_codes == out_code) | (database_codes == "?") | (np.array(out_code) == "?"), axis=1)
        ] = np.NAN

    return scores


def get_individual_seek_identities(individuals=Individual.objects, individual_sightings=Individual_Sighting.objects):
    individuals = (
        individuals.annotate(
            seek_identity_pk=Subquery(
                individual_sightings.filter(
                    individual_id=OuterRef("id"),
                )
                .order_by("-pk")
                .values("seek_identity")[:1]
            )
        )
        .filter(seek_identity_pk__isnull=False)
        .order_by("seek_identity_pk")
    )

    seek_identities = Seek_Identity.objects.filter(
        pk__in=individuals.values_list("seek_identity_pk", flat=True)
    ).order_by("pk")

    return individuals, seek_identities


def score(
    individual_sighting,
    database_individuals=Individual.objects,
    database_individual_sightings=Individual_Sighting.objects,
):
    database_individuals, seek_identities = get_individual_seek_identities(
        database_individuals, database_individual_sightings
    )
    seek_codes = [np.array(seek_identity) for seek_identity in seek_identities]
    seek_scores = score_seek(individual_sighting.seek_identity, seek_codes)

    curvrank_scores = np.zeros_like(seek_scores)

    sum_scores = np.sum([seek_scores, curvrank_scores], axis=0)

    results = pd.DataFrame(
        {
            "individual": database_individuals,
            "sum_score": sum_scores,
            "seek_score": seek_scores,
            "seek_identity": seek_identities,
            "seek_code": seek_codes,
            "curvrank_score": curvrank_scores,
        }
    ).sort_values("sum_score", ascending=False, ignore_index=True)

    return results
