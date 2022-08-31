import numpy as np
from django.contrib.auth.models import AbstractUser
from django.core.validators import ValidationError
from django.db import models
from multiselectfield import MultiSelectField
from polymorphic.models import PolymorphicModel


def NON_POLYMORPHIC_SET_NULL(collector, field, sub_objs, using):
    return models.SET_NULL(collector, field, sub_objs.non_polymorphic(), using)


def NON_POLYMORPHIC_CASCADE(collector, field, sub_objs, using):
    return models.CASCADE(collector, field, sub_objs.non_polymorphic(), using)


class EB_Core_Permisson(models.Model):
    class Meta:
        managed = False

        default_permissions = ()

        permissions = (
            ("main", "Access live portion of EB"),
            ("advanced", "Access advanced features not intended for typical EB use"),
            ("expert", "Qualified as an expert to make final review on labeling"),
        )


class EBUser(AbstractUser):
    """Model representing an ElephantBook user."""

    pass


class Group_Sighting(PolymorphicModel):
    """Model representing a group of elephants spotted at the same time and place."""

    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    datetime = models.DateTimeField(null=True, blank=True, db_index=True)
    json = models.JSONField(null=True, blank=True)
    unphotographed_individuals = models.ManyToManyField("Individual", blank=True)
    notes = models.TextField(default="", blank=True)

    def get_upload_to(self):
        return f"group_sighting/{self.pk}"

    def __str__(self):
        return f"{self.pk}"


class EarthRanger_Sighting(Group_Sighting):
    """Model representing a group of elephants spotted at the same time and place at an EarthRanger event."""

    earthranger_id = models.UUIDField(unique=True, db_index=True)
    earthranger_serial = models.PositiveIntegerField(unique=True, db_index=True)

    def get_upload_to(self):
        return f"earthranger/{self.earthranger_serial}"

    def __str__(self):
        return f"{self.pk} - {self.earthranger_serial}"


class Individual_Sighting(models.Model):
    """Model representing a single elephant spotted at a single time and place."""

    individual = models.ForeignKey("Individual", null=True, blank=True, on_delete=models.PROTECT)
    group_sighting = models.ForeignKey("Group_Sighting", on_delete=models.CASCADE)

    unidentifiable = models.BooleanField(default=False)
    completed = models.BooleanField(default=False)
    expert_reviewed = models.BooleanField(default=False)
    notes = models.TextField(default="", blank=True)

    seek_identity = models.OneToOneField("Seek_Identity", null=True, blank=True, on_delete=models.PROTECT)

    body_condition = models.CharField(
        max_length=1,
        choices=(
            ("1", "1"),
            ("2", "2"),
            ("3", "3"),
            ("4", "4"),
            ("5", "5"),
        ),
        null=True,
        blank=True,
    )

    reaction_index = models.CharField(
        max_length=1,
        choices=(
            ("1", "1"),
            ("2", "2"),
            ("3", "3"),
            ("4", "4"),
        ),
        null=True,
        blank=True,
    )

    class Meta:
        get_latest_by = "group_sighting"

    def __str__(self):
        return f"{self.pk}"


class Musth_Status(models.Model):
    individual_sighting = models.OneToOneField("Individual_Sighting", null=True, blank=True, on_delete=models.CASCADE)

    temporal_secretion = models.CharField(
        max_length=2,
        choices=(
            ("0", "None"),
            ("W", "Wet"),
            ("AM", "Above Mouthline"),
            ("BM", "Below Mouthline"),
        ),
        null=True,
        blank=True,
    )

    temporal_gland = models.CharField(
        max_length=2,
        choices=(
            ("0", "None"),
            ("OS", "Opening Swollen"),
            ("SB", "Swollen/Cheekbone Visible"),
            ("SN", "Swollen/No Cheekbone Visible"),
        ),
        null=True,
        blank=True,
    )

    urine = MultiSelectField(
        choices=(
            ("0", "None"),
            ("S", "Sheath Opening Wet"),
            ("SL", "Sheath & Hind Legs Wet"),
            ("D", "Dribbling"),
            ("PS", "Pungent Smell"),
        ),
        null=True,
        blank=True,
    )


class Subgroup_Sighting(models.Model):
    """Model representing a subgroup of elephants spotted at the same time and place."""

    group_sighting = models.ForeignKey("Group_Sighting", on_delete=models.CASCADE)

    individual_sightings = models.ManyToManyField("Individual_Sighting", blank=True)
    unphotographed_individuals = models.ManyToManyField("Individual", blank=True)

    group_type = models.CharField(
        max_length=1,
        choices=(
            ("0", "Family Unit"),
            ("1", "Family Group"),
            ("2", "Bond Group"),
            ("3", "Bull Group"),
            ("?", "Other"),
        ),
        null=True,
        blank=True,
    )

    notes = models.TextField(default="", blank=True)


class Individual(models.Model):
    """Model representing an elephant identity."""

    name = models.CharField(max_length=128, unique=True, db_index=True)
    notes = models.TextField(default="", blank=True)

    profile = models.ForeignKey("Photo", related_name="+", null=True, blank=True, on_delete=models.PROTECT)

    def __str__(self):
        return f"{self.pk} - {self.name}"


class Photo(PolymorphicModel):
    """Model representing a photo taken in the field."""

    name = models.CharField(max_length=100, unique=True)

    image = models.ImageField(unique=True)
    compressed_image = models.ImageField(unique=True)
    thumbnail = models.ImageField(unique=True, null=True)

    def __str__(self):
        return self.name


class Sighting_Photo(Photo):
    """Model representing a photo associated with a `Group_Sighting` object."""

    group_sighting = models.ForeignKey("Group_Sighting", on_delete=NON_POLYMORPHIC_CASCADE)


class Individual_Photo(Photo):
    """Model representing a photo associated with an `Individual` object."""

    individual = models.ForeignKey("Individual", on_delete=NON_POLYMORPHIC_CASCADE)


class Seek_Identity(models.Model):
    """Model representing a code for the System for Elephant Ear-pattern Knowledge (SEEK) elephant re-identification
    system.
    """

    presence = (("0", "Absence"), ("1", "Presence"))

    gender = models.CharField(
        max_length=1, choices=(("b", "bull"), ("c", "cow"), ("?", "unknown")), null=True, blank=True
    )

    age = models.CharField(
        max_length=1,
        choices=(
            ("6", "1900-1969"),
            ("7", "1970-1979"),
            ("8", "1980-1989"),
            ("9", "1990-1999"),
            ("0", "2000-2009"),
            ("1", "2010-2019"),
            ("2", "2020-2029"),
        ),
        null=True,
        blank=True,
    )

    r_tusk = models.CharField(max_length=1, choices=presence, null=True, blank=True)
    l_tusk = models.CharField(max_length=1, choices=presence, null=True, blank=True)

    r_ear_positions = (("0", "None"), ("7", "Position 7"), ("8", "Position 8"), ("9", "Position 9"))

    l_ear_positions = (("0", "None"), ("3", "Position 3"), ("4", "Position 4"), ("5", "Position 5"))

    r_prom_tear = models.CharField(max_length=1, choices=r_ear_positions, null=True, blank=True)
    r_prom_hole = models.CharField(max_length=1, choices=r_ear_positions, null=True, blank=True)
    r_sec_tear = models.CharField(max_length=1, choices=r_ear_positions, null=True, blank=True)
    r_sec_hole = models.CharField(max_length=1, choices=r_ear_positions, null=True, blank=True)
    l_prom_tear = models.CharField(max_length=1, choices=l_ear_positions, null=True, blank=True)
    l_prom_hole = models.CharField(max_length=1, choices=l_ear_positions, null=True, blank=True)
    l_sec_tear = models.CharField(max_length=1, choices=l_ear_positions, null=True, blank=True)
    l_sec_hole = models.CharField(max_length=1, choices=l_ear_positions, null=True, blank=True)

    r_extreme = models.CharField(max_length=1, choices=presence, null=True, blank=True)
    l_extreme = models.CharField(max_length=1, choices=presence, null=True, blank=True)

    r_special = models.CharField(max_length=1, choices=presence, null=True, blank=True)
    l_special = models.CharField(max_length=1, choices=presence, null=True, blank=True)
    body_special = models.CharField(max_length=1, choices=presence, null=True, blank=True)

    def __str__(self):
        return "".join(
            [
                "?" if c is None else c
                for c in [
                    self.gender,
                    self.age,
                    "T",
                    self.r_tusk,
                    self.l_tusk,
                    "E",
                    self.r_prom_tear,
                    self.r_prom_hole,
                    self.r_sec_tear,
                    self.r_sec_hole,
                    "-",
                    self.l_prom_tear,
                    self.l_prom_hole,
                    self.l_sec_tear,
                    self.l_sec_hole,
                    "X",
                    self.r_extreme,
                    self.l_extreme,
                    "S",
                    self.r_special,
                    self.l_special,
                    self.body_special,
                ]
            ]
        )

    def __array__(self, dtype=None):
        return np.array(
            [
                "?" if c is None else c
                for c in [
                    self.gender,
                    self.age,
                    self.r_tusk,
                    self.l_tusk,
                    self.r_prom_tear,
                    self.r_prom_hole,
                    self.r_sec_tear,
                    self.r_sec_hole,
                    self.l_prom_tear,
                    self.l_prom_hole,
                    self.l_sec_tear,
                    self.l_sec_hole,
                    self.r_extreme,
                    self.l_extreme,
                    self.r_special,
                    self.l_special,
                    self.body_special,
                ]
            ],
            dtype=dtype,
        )


class Elephant_Voices_Identity(models.Model):
    """Model representing a code for the Elephant Voices elephant re-identification system."""

    sex_vals = (("0", "unknown"), ("1", "female"), ("2", "male"))

    sex = models.CharField(max_length=1, choices=sex_vals, null=True, blank=True)

    living_status_vals = (("0", "alive"), ("1", "dead"))

    living_status = models.CharField(max_length=1, choices=living_status_vals, null=True, blank=True)

    life_stage_vals = (
        ("0", "unknown"),
        ("1", "senescing adult"),
        ("2", "prime adult"),
        ("3", "adult"),
        ("4", "young adult"),
        ("5", "sub-adult"),
    )

    life_stage = models.CharField(max_length=1, choices=life_stage_vals, null=True, blank=True)

    tusk_vals = (("0", "unknown"), ("1", "present"), ("2", "missing"))

    tusk = models.CharField(max_length=1, choices=tusk_vals, null=True, blank=True)

    tusk_attribute_vals = (
        ("0", "three tusks"),
        ("1", "broken left"),
        ("2", "broken right"),
        ("3", "equal length"),
        ("4", "shorter left"),
        ("5", "shorter right"),
        ("6", "very shorter"),
        ("7", "very long"),
        ("8", "very thin"),
        ("9", "very thick"),
        ("10", "very slender"),
        ("11", "symmetric"),
        ("12", "higher left"),
        ("13", "higher right"),
        ("14", "up curved"),
        ("15", "straight"),
        ("16", "splayed"),
        ("17", "convergent"),
        ("18", "crossed"),
        ("19", "skewed"),
        ("20", "wonky"),
    )

    tusk_attribute = MultiSelectField(choices=tusk_attribute_vals, null=True, blank=True)

    ear_condition_vals = (
        ("0", "completely smooth"),
        ("1", "smooth with tiny nicknames"),
        ("2", "serrated"),
        ("3", "ragged"),
        ("4", "wart/bump"),
        ("5", "prominent veins"),
        ("6", "crinkle"),
        ("7", "fold"),
        ("8", "damaged"),
        ("9", "curtain"),
        ("10", "flop"),
        ("11", "droopy"),
    )

    ear_condition = MultiSelectField(choices=ear_condition_vals, null=True, blank=True)

    ear_notch_vals = (
        ("0", "unusual notch"),
        ("1", "outstanding notch or tear"),
        ("2", "v-notch"),
        ("3", "u-notch"),
        ("4", "cup-notch"),
        ("5", "dip-notch"),
        ("6", "scoop-notch"),
        ("7", "square-notch"),
    )

    ear_notch = MultiSelectField(choices=ear_notch_vals, null=True, blank=True)

    body_type_vals = (
        ("0", "collar"),
        ("1", "bump/lump right"),
        ("2", "bump/lump left"),
        ("3", "permanently lame"),
        ("4", "head low"),
    )

    body_type = MultiSelectField(choices=body_type_vals, null=True, blank=True)

    trunk_face_features_vals = (
        ("0", "strange skin pattern"),
        ("1", "blind in one eye"),
        ("2", "slit cut trunk"),
        ("3", "other trunk injury"),
        ("4", "wart/bump trunk"),
        ("5", "wart/bump face"),
        ("6", "wrinkled forehead"),
        ("7", "pointed forehead"),
        ("8", "chopped trunk"),
        ("9", "lip damage"),
    )

    trunk_face_features = MultiSelectField(choices=trunk_face_features_vals, null=True, blank=True)

    tail_features_vals = (
        ("0", "no tail"),
        ("1", "half tail"),
        ("2", "kinky tail"),
        ("3", "short tail"),
        ("4", "no tail hairs"),
    )

    tail_features = MultiSelectField(choices=tail_features_vals, null=True, blank=True)


class Bounding_Box(PolymorphicModel):
    """Model representing a bounding box on a `Photo` object."""

    photo = models.ForeignKey("Photo", on_delete=NON_POLYMORPHIC_CASCADE)

    x = models.FloatField()
    y = models.FloatField()
    w = models.FloatField()
    h = models.FloatField()

    def __str__(self):
        return f"[{self.x},{self.y},{self.w},{self.h}]"


class Sighting_Bounding_Box(Bounding_Box):
    """Model representing a bounding box of an elephant associated with an `Individual_Sighting`."""

    individual_sighting = models.ForeignKey(
        "Individual_Sighting", on_delete=NON_POLYMORPHIC_CASCADE, null=True, blank=True
    )

    def save(self, *args, **kwargs):
        if type(self.photo) is not Sighting_Photo:
            raise ValidationError("self.photo is not of type Sighting_Photo")

        super().save(*args, **kwargs)


class Individual_Bounding_Box(Bounding_Box):
    """Model representing a bounding box of an elephant associated with an `Individual`."""

    individual = models.ForeignKey("Individual", on_delete=NON_POLYMORPHIC_CASCADE, null=True, blank=True)

    def save(self, *args, **kwargs):
        if type(self.photo) is not Individual_Photo:
            raise ValidationError("self.photo is not of type Individual_Photo")

        super().save(*args, **kwargs)


class Injury(models.Model):
    """Model representing a spotted injury."""

    individual_sighting = models.ForeignKey("Individual_Sighting", on_delete=models.CASCADE)

    injury_locations = (
        ("0", "0 Non-Specific"),
        ("1", "1 Trunk"),
        ("2", "2 Mouth"),
        ("3", "3 Chest"),
        ("4", "4 Tail"),
        ("5", "5 Right Head A"),
        ("6", "6 Right Head B"),
        ("7", "7 Right Head C"),
        ("8", "8 Right Body A"),
        ("9", "9 Right Body B"),
        ("10", "10 Right Body C"),
        ("11", "11 Right Body D"),
        ("12", "12 Right Body E"),
        ("13", "13 Right Body F"),
        ("14", "14 Right Rear Leg Lower Outer"),
        ("15", "15 Right Rear Leg Lower Inner"),
        ("16", "16 Right Rear Leg Upper Outer"),
        ("17", "17 Right Rear Leg Upper Inner"),
        ("18", "18 Right Front Leg Lower Outer"),
        ("19", "19 Right Front Leg Lower Inner"),
        ("20", "20 Right Front Leg Upper Outer"),
        ("21", "21 Right Front Leg Upper Inner"),
        ("22", "22 Right Ear Outer"),
        ("23", "23 Right Ear Inner"),
        ("24", "24 Left Head A"),
        ("25", "25 Left Head B"),
        ("26", "26 Left Head C"),
        ("27", "27 Left Body A"),
        ("28", "28 Left Body B"),
        ("29", "29 Left Body C"),
        ("30", "30 Left Body D"),
        ("31", "31 Left Body E"),
        ("32", "32 Left Body F"),
        ("33", "33 Left Rear Leg Lower Outer"),
        ("34", "34 Left Rear Leg Lower Inner"),
        ("35", "35 Left Rear Leg Upper Outer"),
        ("36", "36 Left Rear Leg Upper Inner"),
        ("37", "37 Left Front Leg Lower Outer"),
        ("38", "38 Left Front Leg Lower Inner"),
        ("39", "39 Left Front Leg Upper Outer"),
        ("40", "40 Left Front Leg Upper Inner"),
        ("41", "41 Left Ear Outer"),
        ("42", "42 Left Ear Inner"),
        ("43", "43 Genitals"),
    )

    location = MultiSelectField(choices=injury_locations, null=True, blank=True)

    status_vals = (
        ("0", "old"),
        ("1", "active"),
        ("2", "healed"),
        ("3", "not visible"),
    )

    status = models.CharField(max_length=1, choices=status_vals, null=True, blank=True)

    cause_vals = (
        ("0", "arrow"),
        ("1", "spear"),
        ("2", "snare"),
        ("3", "hyperkeratosis"),
        ("4", "unknown"),
        ("5", "other"),
    )

    cause = models.CharField(max_length=1, choices=cause_vals, null=True, blank=True)

    notes = models.TextField(default="", blank=True)
