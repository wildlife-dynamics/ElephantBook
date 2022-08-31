from rest_framework import serializers

from eb_core.models import (
    EarthRanger_Sighting,
    Individual,
    Individual_Sighting,
    Seek_Identity,
)


class EarthRangerSightingSerializer(serializers.ModelSerializer):
    class Meta:
        model = EarthRanger_Sighting
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.context.get("include_json", False):
            self.fields.pop("json")


class SeekIdentitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Seek_Identity
        fields = "__all__"


class IndividualSightingSerializer(serializers.ModelSerializer):
    seek_identity = SeekIdentitySerializer()

    class Meta:
        model = Individual_Sighting
        fields = "__all__"


class IndividualSerializer(serializers.ModelSerializer):
    latest_seek_identity = serializers.IntegerField()

    class Meta:
        model = Individual
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.context.get("include_latest_seek_identity", False):
            self.fields.pop("latest_seek_identity")
