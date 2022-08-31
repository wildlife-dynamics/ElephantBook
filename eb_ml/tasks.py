import os

import numpy as np
import pandas as pd
import torch
import torchvision
from celery import shared_task
from django.contrib.postgres.expressions import ArraySubquery
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import OuterRef
from PIL import Image, ImageOps
from torchvision import transforms

from eb_core.models import (
    Individual,
    Individual_Sighting,
    Photo,
    Sighting_Bounding_Box,
)
from eb_core.utils import get_individual_seek_identities, score_seek
from ElephantBook.settings import BASE_DIR

from .models import Bbox_ML, Coco_Bbox, Ear_Bbox, Embedding, Photo_ML, Scoring


class Detector:
    @classmethod
    def detect(cls, photo_mls, force=False, **kwargs):
        valid_photo_mls = []
        for photo_ml in photo_mls:
            if photo_ml.detections is None:
                valid_photo_mls.append(photo_ml)
                photo_ml.detections = {cls.__name__: None}
                photo_ml.save()
            elif photo_ml.detections.get(cls.__name__) is None:
                valid_photo_mls.append(photo_ml)
                photo_ml.detections.update({cls.__name__: None})
                photo_ml.save()
        if not force:
            photo_mls = valid_photo_mls

        if photo_mls:
            return cls._detect(photo_mls, **kwargs)
        return []

    @classmethod
    def _detect(cls, photo_mls, **kwargs):
        return NotImplemented


class EarDetector(Detector):
    @classmethod
    def _detect(cls, photo_mls):
        bboxes = []
        model = torch.hub.load(
            "ultralytics/yolov5", "custom", path=os.path.join(BASE_DIR, "eb_ml/data/ear_YOLOv5_n.pt")
        )
        for photo_ml in photo_mls:
            photo_ml.detections[cls.__name__] = (
                model(ImageOps.exif_transpose(Image.open(photo_ml.photo.compressed_image.path))).xywhn[0].tolist()
            )
            photo_ml.save()

            photo_ml.bbox_ml_set.instance_of(Ear_Bbox).delete()
            for x, y, w, h, conf, bbox_cls in photo_ml.detections[cls.__name__]:
                bbox = Ear_Bbox(
                    photo_ml=photo_ml,
                    cls=bbox_cls,
                    conf=conf,
                    x1=x - w / 2,
                    y1=y - h / 2,
                    x2=x + w / 2,
                    y2=y + h / 2,
                )
                bbox.save()
                bboxes.append(bbox)
        return bboxes


class CocoDetector(Detector):
    @classmethod
    def _detect(cls, photo_mls):
        bboxes = []
        model = torch.hub.load("ultralytics/yolov5", "yolov5n")
        for photo_ml in photo_mls:
            photo_ml.detections[cls.__name__] = (
                model(ImageOps.exif_transpose(Image.open(photo_ml.photo.compressed_image.path))).xywhn[0].tolist()
            )
            photo_ml.save()

            photo_ml.bbox_ml_set.instance_of(Coco_Bbox).delete()
            for x, y, w, h, conf, bbox_cls in photo_ml.detections[cls.__name__]:
                bbox = Coco_Bbox(
                    photo_ml=photo_ml,
                    cls=bbox_cls,
                    conf=conf,
                    x1=x - w / 2,
                    y1=y - h / 2,
                    x2=x + w / 2,
                    y2=y + h / 2,
                )
                bbox.save()
                bboxes.append(bbox)
        return bboxes


@shared_task
def detect(photo_pks, force=False):
    photos = Photo.objects.filter(pk__in=photo_pks)

    photo_mls = []
    for photo in photos:
        try:
            photo_ml = photo.photo_ml
        except ObjectDoesNotExist:
            photo_ml = Photo_ML()
            photo_ml.photo = photo
            photo_ml.save()
        photo_mls.append(photo_ml)

    bboxes = []
    for detector in [CocoDetector, EarDetector]:
        bboxes.extend(detector.detect(photo_mls, force=force))

    if bboxes:
        extract_features.delay([bbox.pk for bbox in bboxes], force=force)

    associate_bboxes.delay(list(photos.values_list("photo_ml", flat=True)))


class FeatureExtractor:
    embedding_class = -1

    @classmethod
    def extract_features(cls, bbox_mls, force=False, **kwargs):
        bbox_mls = [bbox_ml for bbox_ml in bbox_mls if cls.is_valid_bbox(bbox_ml)]
        if not force:
            bbox_mls = [bbox_ml for bbox_ml in bbox_mls if not bbox_ml.embedding_set.filter(cls=cls.embedding_class)]
        if bbox_mls:
            return cls._extract_features(bbox_mls, **kwargs)
        return []

    @classmethod
    def _extract_features(cls, bbox_mls, **kwargs):
        return NotImplemented

    @classmethod
    def _is_valid_bbox(cls, bbox_ml, **kwargs):
        return NotImplemented

    @classmethod
    def _normalize(cls, x):
        x = x - x.mean()
        return x / np.linalg.norm(x)


class RightEarFeatureExtractor(FeatureExtractor):
    embedding_class = 1

    @classmethod
    def is_valid_bbox(cls, bbox_ml):
        return isinstance(bbox_ml, Ear_Bbox) and bbox_ml.cls == 0

    @classmethod
    def _extract_features(cls, bbox_mls, flip=False):
        model = torchvision.models.resnet50()
        model.fc = torch.nn.Sequential(
            torch.nn.Linear(model.fc.in_features, 512),
            torch.nn.BatchNorm1d(512),
            torch.nn.ReLU(inplace=True),
        )
        model.load_state_dict(torch.load(os.path.join(BASE_DIR, "eb_ml/data/ear_piev2_rnet50.pt")))
        model.eval()

        transform = transforms.Compose(
            [
                transforms.Resize((256, 256)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )

        embeddings = []
        with torch.no_grad():
            for bbox_ml in bbox_mls:
                bbox_ml.embedding_set.filter(cls=cls.embedding_class).delete()

                im = ImageOps.exif_transpose(Image.open(bbox_ml.photo_ml.photo.compressed_image.path))
                im = im.crop(
                    (bbox_ml.x1 * im.width, bbox_ml.y1 * im.height, bbox_ml.x2 * im.width, bbox_ml.y2 * im.height)
                )

                embedding = Embedding.objects.create(
                    cls=cls.embedding_class,
                    bbox_ml=bbox_ml,
                    data=cls._normalize(model(transform(im)[None]).cpu().numpy()[0]).tolist(),
                )

                embeddings.append(embedding)
        return embeddings


class LeftEarFeatureExtractor(RightEarFeatureExtractor):
    embedding_class = 2

    @classmethod
    def is_valid_bbox(cls, bbox_ml):
        return isinstance(bbox_ml, Ear_Bbox) and bbox_ml.cls == 1


@shared_task
def extract_features(bbox_ml_pks, force=False):
    bbox_mls = Bbox_ML.objects.filter(pk__in=bbox_ml_pks)

    embeddings = []
    for feature_extractor in [RightEarFeatureExtractor, LeftEarFeatureExtractor]:
        embeddings.extend(feature_extractor.extract_features(bbox_mls, force=force))


def bbox_intersection(bbox1, bbox2):
    x_left = max(bbox1["x1"], bbox2["x1"])
    y_top = max(bbox1["y1"], bbox2["y1"])
    x_right = min(bbox1["x2"], bbox2["x2"])
    y_bottom = min(bbox1["y2"], bbox2["y2"])

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    return (x_right - x_left) * (y_bottom - y_top)


def bbox_union(bbox1, bbox2):
    return bbox_area(bbox1) + bbox_area(bbox2) - bbox_intersection(bbox1, bbox2)


def bbox_area(bbox):
    return (bbox["x2"] - bbox["x1"]) * (bbox["y2"] - bbox["y1"])


def bbox_iou(bbox1, bbox2):
    return bbox_intersection(bbox1, bbox2) / bbox_union(bbox1, bbox2)


@shared_task
def associate_bboxes(photo_ml_pks):
    photo_mls = Photo_ML.objects.filter(pk__in=photo_ml_pks)

    for photo_ml in photo_mls:
        bounding_boxes = photo_ml.photo.bounding_box_set.all()
        bounding_box_dicts = [
            {"x1": bbox.x, "y1": bbox.y, "x2": bbox.x + bbox.w, "y2": bbox.y + bbox.h} for bbox in bounding_boxes
        ]

        for bbox_ml in photo_ml.bbox_ml_set.all():
            bbox_ml_dict = {"x1": bbox_ml.x1, "y1": bbox_ml.y1, "x2": bbox_ml.x2, "y2": bbox_ml.y2}
            if isinstance(bbox_ml, Coco_Bbox) and bbox_ml.cls == 20:
                for bbox, bbox_dict in zip(bounding_boxes, bounding_box_dicts):
                    if bbox_iou(bbox_ml_dict, bbox_dict) > 0.7:
                        bbox_ml.bounding_box = bbox
                        break
                else:
                    bbox_ml.bounding_box = None
                bbox_ml.save()
            elif isinstance(bbox_ml, Ear_Bbox):
                for bbox, bbox_dict in zip(bounding_boxes, bounding_box_dicts):
                    if bbox_intersection(bbox_ml_dict, bbox_dict) / bbox_area(bbox_ml_dict) > 0.9:
                        bbox_ml.bounding_box = bbox
                        break
                else:
                    bbox_ml.bounding_box = None
                bbox_ml.save()


def get_emb_scores(
    out_individual_sightings,
    emb_cls,
    database_individuals=Individual.objects,
    database_individual_sightings=Individual_Sighting.objects,
):
    try:
        out_ids, out_counts, out_embeddings = zip(
            *[
                (individual_id, len(data), data)
                for individual_id, data in out_individual_sightings.annotate(
                    data_array=ArraySubquery(
                        Embedding.objects.filter(
                            cls=emb_cls,
                            bbox_ml__bounding_box__in=Sighting_Bounding_Box.objects.filter(
                                individual_sighting=OuterRef(OuterRef("pk"))
                            ),
                        ).values("data")
                    )
                ).values_list("id", "data_array")
                if data
            ]
        )

        database_ids, database_counts, database_embeddings = zip(
            *[
                (individual_id, len(data), data)
                for individual_id, data in database_individuals.all()
                .annotate(
                    data_array=ArraySubquery(
                        Embedding.objects.filter(
                            cls=emb_cls,
                            bbox_ml__bounding_box__in=Sighting_Bounding_Box.objects.filter(
                                individual_sighting__in=database_individual_sightings.all(),
                                individual_sighting__individual=OuterRef(OuterRef("pk")),
                            ),
                        ).values("data")
                    )
                )
                .values_list("id", "data_array")
                if data
            ]
        )
    except ValueError:
        return np.full((out_individual_sightings.count(), database_individuals.count()), np.nan)

    scores = np.full((out_individual_sightings.count(), database_individuals.count()), np.nan)

    scores[
        np.ix_(
            np.in1d(out_individual_sightings.values_list("id", flat=True), out_ids),
            np.in1d(database_individuals.values_list("id", flat=True), database_ids),
        )
    ] = (
        0.5
        + np.maximum.reduceat(
            np.maximum.reduceat(
                (np.concatenate(out_embeddings) @ np.concatenate(database_embeddings).T),
                np.r_[0, np.cumsum(out_counts[:-1])],
            ),
            np.r_[0, np.cumsum(database_counts[:-1])],
            axis=1,
        )
        / 2
    )

    return scores


@shared_task
def update_scorings(
    out_individual_sightings,
    database_individuals=Individual.objects,
    database_individual_sightings=Individual_Sighting.objects,
):
    if not isinstance(out_individual_sightings[0], Individual_Sighting):
        out_individual_sightings = Individual_Sighting.objects.filter(pk__in=out_individual_sightings)

    database_individuals, seek_identities = get_individual_seek_identities(
        individuals=database_individuals, individual_sightings=database_individual_sightings
    )
    seek_strings = [str(seek_identity) for seek_identity in seek_identities]

    seek_scores = np.array(
        [
            score_seek(out_individual_sighting.seek_identity, seek_identities)
            for out_individual_sighting in out_individual_sightings
        ]
    )

    right_ear_emb_scores = get_emb_scores(
        out_individual_sightings=out_individual_sightings,
        emb_cls=1,
        database_individuals=database_individuals,
        database_individual_sightings=database_individual_sightings,
    )

    left_ear_emb_scores = get_emb_scores(
        out_individual_sightings=out_individual_sightings,
        emb_cls=2,
        database_individuals=database_individuals,
        database_individual_sightings=database_individual_sightings,
    )

    index = pd.Index(database_individuals.values_list("pk", flat=True), name="individual")

    scores = np.array(
        [
            seek_scores,
            right_ear_emb_scores,
            left_ear_emb_scores,
        ]
    )

    columns = np.array(
        [
            "seek_score",
            "right_ear_emb_score",
            "left_ear_emb_score",
        ]
    )

    weights = np.array(
        [
            1,
            0.25,
            0.25,
        ]
    )

    total_scores = np.ma.average(np.ma.MaskedArray(scores, mask=np.isnan(scores)), weights=weights, axis=0)

    for i, out_individual_sighting in enumerate(out_individual_sightings):
        df = pd.DataFrame(data=scores[:, i].T, columns=columns, index=index)
        df["score"] = total_scores[i]
        df["seek_code"] = seek_strings

        Scoring.objects.update_or_create(
            individual_sighting=out_individual_sighting,
            defaults={
                "data": df.sort_values("score", ascending=False).reset_index(level=0).fillna("NaN").to_dict("list")
            },
        )


@shared_task
def fill_sighting_scoring():
    out_individual_sightings = Individual_Sighting.objects.filter(
        unidentifiable=False,
        completed=False,
        seek_identity__isnull=False,
        scoring__isnull=True,
    )
    if out_individual_sightings.exists():
        update_scorings(out_individual_sightings)


@shared_task
def update_all_sighting_scoring():
    if Individual_Sighting.objects.exists():
        update_scorings(Individual_Sighting.objects.all())
