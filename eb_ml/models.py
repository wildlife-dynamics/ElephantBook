from django.db import models
from polymorphic.models import PolymorphicModel

from eb_core.models import NON_POLYMORPHIC_CASCADE, NON_POLYMORPHIC_SET_NULL


class Photo_ML(models.Model):
    """Model representing ML data for a Photo object."""

    photo = models.OneToOneField("eb_core.Photo", on_delete=models.CASCADE)

    detections = models.JSONField(default=dict)


class Bbox_ML(PolymorphicModel):
    cls_map = {}

    photo_ml = models.ForeignKey("Photo_ML", on_delete=NON_POLYMORPHIC_CASCADE)
    bounding_box = models.ForeignKey("eb_core.Bounding_Box", null=True, blank=True, on_delete=NON_POLYMORPHIC_SET_NULL)

    cls = models.PositiveIntegerField(null=True, blank=True)

    conf = models.FloatField(null=True, blank=True)

    x1 = models.FloatField(null=True, blank=True)
    y1 = models.FloatField(null=True, blank=True)
    x2 = models.FloatField(null=True, blank=True)
    y2 = models.FloatField(null=True, blank=True)


class Ear_Bbox(Bbox_ML):
    cls_map = {
        0: "right",
        1: "left",
    }


class Coco_Bbox(Bbox_ML):
    cls_map = {
        0: "person",
        1: "bicycle",
        2: "car",
        3: "motorcycle",
        4: "airplane",
        5: "bus",
        6: "train",
        7: "truck",
        8: "boat",
        9: "traffic light",
        10: "fire hydrant",
        11: "stop sign",
        12: "parking meter",
        13: "bench",
        14: "bird",
        15: "cat",
        16: "dog",
        17: "horse",
        18: "sheep",
        19: "cow",
        20: "elephant",
        21: "bear",
        22: "zebra",
        23: "giraffe",
        24: "backpack",
        25: "umbrella",
        26: "handbag",
        27: "tie",
        28: "suitcase",
        29: "frisbee",
        30: "skis",
        31: "snowboard",
        32: "sports ball",
        33: "kite",
        34: "baseball bat",
        35: "baseball glove",
        36: "skateboard",
        37: "surfboard",
        38: "tennis racket",
        39: "bottle",
        40: "wine glass",
        41: "cup",
        42: "fork",
        43: "knife",
        44: "spoon",
        45: "bowl",
        46: "banana",
        47: "apple",
        48: "sandwich",
        49: "orange",
        50: "broccoli",
        51: "carrot",
        52: "hot dog",
        53: "pizza",
        54: "donut",
        55: "cake",
        56: "chair",
        57: "couch",
        58: "potted plant",
        59: "bed",
        60: "dining table",
        61: "toilet",
        62: "tv",
        63: "laptop",
        64: "mouse",
        65: "remote",
        66: "keyboard",
        67: "cell phone",
        68: "microwave",
        69: "oven",
        70: "toaster",
        71: "sink",
        72: "refrigerator",
        73: "book",
        74: "clock",
        75: "vase",
        76: "scissors",
        77: "teddy bear",
        78: "hair drier",
        79: "toothbrush",
    }


class Embedding(models.Model):
    cls_map = {
        1: "right ear",
        2: "left ear",
    }  # Could wrap into EmbeddingConfig model

    cls = models.PositiveIntegerField(null=True, blank=True)

    data = models.JSONField()

    bbox_ml = models.ForeignKey("Bbox_ML", on_delete=models.CASCADE)


class Scoring(models.Model):
    individual_sighting = models.OneToOneField("eb_core.Individual_Sighting", on_delete=models.CASCADE)
    last_updated = models.DateTimeField(auto_now=True)

    data = models.JSONField()
