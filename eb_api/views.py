import json

from django.db.models import OuterRef, Subquery
from rest_framework import generics

from eb_core.models import (
    EarthRanger_Sighting,
    Individual,
    Individual_Sighting,
    Seek_Identity,
)

from .serializers import (
    EarthRangerSightingSerializer,
    IndividualSerializer,
    IndividualSightingSerializer,
    SeekIdentitySerializer,
)


def _is_truthy(x):
    return str(x).lower() in {"true", "1"}


class EarthRangerSightingView(generics.ListAPIView):
    """
    Parameters
    ----------
    id
    earthranger_id
    earthranger_serial
    individual_sighting
    individual
    individual_name
    start_time
    end_time
    bbox : "{x1},{y1},{x2},{y2}"
        WGS 84 bounds to filter sightings to
    include_json : true/false, default False
    filter : dict(key, value)
        Filter to be applied directly to queryset
    """

    serializer_class = EarthRangerSightingSerializer

    def get_serializer_context(self):
        query_params = self.request.query_params if self.request and hasattr(self.request, "query_params") else {}

        context = super().get_serializer_context()

        context["include_json"] = _is_truthy(query_params.get("include_json"))

        return context

    def get_queryset(self):
        query_params = self.request.query_params

        queryset = EarthRanger_Sighting.objects.all()

        ids = query_params.getlist("id")
        if ids:
            queryset = queryset.filter(id__in=ids)

        earthranger_ids = query_params.getlist("earthranger_id")
        if earthranger_ids:
            queryset = queryset.filter(earthranger_id__in=earthranger_ids)

        earthranger_serials = query_params.getlist("earthranger_serial")
        if earthranger_serials:
            queryset = queryset.filter(earthranger_serial__in=earthranger_serials)

        individual_sightings = query_params.getlist("individual_sighting")
        if individual_sightings:
            queryset = queryset.filter(individual_sighting__in=individual_sightings).distinct()

        individuals = query_params.getlist("individual")
        if individuals:
            queryset = queryset.filter(individual_sighting__individual__in=individuals).distinct()

        individual_names = query_params.getlist("individual_name")
        if individual_names:
            queryset = queryset.filter(individual_sighting__individual__name__in=individual_names).distinct()

        start_times = query_params.getlist("start_time")
        if start_times:
            for start_time in start_times:
                queryset = queryset.filter(datetime__gte=start_time)

        end_times = query_params.getlist("end_time")
        if end_times:
            for end_time in end_times:
                queryset = queryset.filter(datetime__lte=end_time)

        bboxes = query_params.getlist("bbox")
        if bboxes:
            for bbox in bboxes:
                x1, y1, x2, y2 = bbox.split(",")
                queryset = queryset.filter(
                    individual_sighting__group_sighting__lat__range=(y1, y2),
                    individual_sighting__group_sighting__lon__range=(x1, x2),
                ).distinct()

        individual_sightings = query_params.getlist("individual_sighting")
        if individual_sightings:
            queryset = queryset.filter(individual_sighting__in=individual_sightings).distinct()

        filters = query_params.getlist("filter")
        if filters:
            queryset = queryset.filter(**{k: v for filter in filters for k, v in json.loads(filter).items()})

        return queryset


class IndividualSightingView(generics.ListAPIView):
    """
    Parameters
    ----------
    id
    group_sighting
    earthranger_id
    earthranger_serial
    individual_sighting
    individual
    individual_name
    start_time
    end_time
    bbox : "{x1},{y1},{x2},{y2}"
        WGS 84 bounds to filter sightings to
    completed
    unidentifiable
    expert_reviewed
    filter : dict(key, value)
        Filter to be applied directly to queryset
    """

    serializer_class = IndividualSightingSerializer

    def get_queryset(self):
        query_params = self.request.query_params

        queryset = Individual_Sighting.objects.all()

        ids = query_params.getlist("id")
        if ids:
            queryset = queryset.filter(id__in=ids)

        group_sightings = query_params.getlist("group_sighting")
        if group_sightings:
            queryset = queryset.filter(group_sighting__in=group_sightings)

        earthranger_ids = query_params.getlist("earthranger_id")
        if earthranger_ids:
            queryset = queryset.filter(group_sighting__earthranger_sighting__earthranger_id__in=earthranger_ids)

        earthranger_serials = query_params.getlist("earthranger_serial")
        if earthranger_serials:
            queryset = queryset.filter(group_sighting__earthranger_sighting__earthranger_serial__in=earthranger_serials)

        individuals = query_params.getlist("individual")
        if individuals:
            queryset = queryset.filter(individual__in=individuals).distinct()

        individual_names = query_params.getlist("individual_name")
        if individual_names:
            queryset = queryset.filter(individual__name__in=individual_names).distinct()

        start_times = query_params.getlist("start_time")
        if start_times:
            for start_time in start_times:
                queryset = queryset.filter(group_sighting__datetime__gte=start_time)

        end_times = query_params.getlist("end_time")
        if end_times:
            for end_time in end_times:
                queryset = queryset.filter(group_sighting__datetime__lte=end_time)

        bboxes = query_params.getlist("bbox")
        if bboxes:
            for bbox in bboxes:
                x1, y1, x2, y2 = bbox.split(",")
                queryset = queryset.filter(
                    individual_sighting__group_sighting__lat__range=(y1, y2),
                    individual_sighting__group_sighting__lon__range=(x1, x2),
                ).distinct()

        completed = query_params.get("completed")
        if completed:
            queryset = queryset.filter(completed=completed)

        unidentifiable = query_params.get("unidentifiable")
        if unidentifiable:
            queryset = queryset.filter(unidentifiable=unidentifiable)

        expert_reviewed = query_params.get("expert_reviewed")
        if expert_reviewed:
            queryset = queryset.filter(expert_reviewed=expert_reviewed)

        filters = query_params.getlist("filter")
        if filters:
            queryset = queryset.filter(**{k: v for filter in filters for k, v in json.loads(filter).items()})

        return queryset


class IndividualView(generics.ListAPIView):
    """
    Parameters
    ----------
    id
    name
    group_sighting
    earthranger_id
    earthranger_serial
    individual_sighting
    start_time
    end_time
    bbox : "{x1},{y1},{x2},{y2}"
        WGS 84 bounds to filter sightings to
    include_latest_seek : true/false
    filter : dict(key, value)
        Filter to be applied directly to queryset
    """

    serializer_class = IndividualSerializer

    def get_serializer_context(self):
        query_params = self.request.query_params if self.request and hasattr(self.request, "query_params") else {}

        context = super().get_serializer_context()

        context["include_latest_seek_identity"] = _is_truthy(query_params.get("include_latest_seek_identity"))

        return context

    def get_queryset(self):
        query_params = self.request.query_params

        queryset = Individual.objects.all()

        ids = query_params.getlist("id")
        if ids:
            queryset = queryset.filter(id__in=ids)

        names = query_params.getlist("name")
        if names:
            queryset = queryset.filter(name__in=names)

        individual_sightings = query_params.getlist("individual_sighting")
        if individual_sightings:
            queryset = queryset.filter(individual_sighting__in=individual_sightings).distinct()

        group_sightings = query_params.getlist("group_sighting")
        if individual_sightings:
            queryset = queryset.filter(individual_sighting__group_sighting__in=group_sightings).distinct()

        earthranger_ids = query_params.getlist("earthranger_id")
        if earthranger_ids:
            queryset = queryset.filter(
                individual_sighting__group_sighting__earthranger_sighting__earthranger_id__in=earthranger_ids
            )

        earthranger_serials = query_params.getlist("earthranger_serial")
        if earthranger_serials:
            queryset = queryset.filter(
                individual_sighting__group_sighting__earthranger_sighting__earthranger_serial__in=earthranger_serials
            )

        start_times = query_params.getlist("start_time")
        if start_times:
            for start_time in start_times:
                queryset = queryset.filter(individual_sighting__group_sighting__datetime__gte=start_time).distinct()

        end_times = query_params.getlist("end_time")
        if end_times:
            for end_time in end_times:
                queryset = queryset.filter(individual_sighting__group_sighting__datetime__lte=end_time).distinct()

        bboxes = query_params.getlist("bbox")
        if bboxes:
            for bbox in bboxes:
                x1, y1, x2, y2 = bbox.split(",")
                queryset = queryset.filter(
                    individual_sighting__group_sighting__lat__range=(y1, y2),
                    individual_sighting__group_sighting__lon__range=(x1, x2),
                ).distinct()

        include_latest_seek_identity = _is_truthy(query_params.get("include_latest_seek_identity"))
        if include_latest_seek_identity:
            queryset = queryset.annotate(
                latest_seek_identity=Subquery(
                    Individual_Sighting.objects.filter(
                        individual_id=OuterRef("id"),
                    )
                    .order_by("-pk")
                    .values("seek_identity")[:1]
                )
            )

        filters = query_params.getlist("filter")
        if filters:
            queryset = queryset.filter(**{k: v for filter in filters for k, v in json.loads(filter).items()})

        return queryset


class SeekIdentityView(generics.ListAPIView):
    """
    Parameters
    ----------
    id
    individual
    individual_name
    group_sighting
    earthranger_id
    earthranger_serial
    individual_sighting
    filter : dict(key, value)
        Filter to be applied directly to queryset
    """

    serializer_class = SeekIdentitySerializer

    def get_queryset(self):
        query_params = self.request.query_params

        queryset = Seek_Identity.objects.all()

        ids = query_params.getlist("id")
        if ids:
            queryset = queryset.filter(id__in=ids)

        individuals = query_params.getlist("individuals")
        if individuals:
            queryset = queryset.filter(individual_sighting__individual__in=individuals)

        individual_names = query_params.getlist("individual_name")
        if individual_names:
            queryset = queryset.filter(individual_sighting__individual__name__in=individual_names)

        individual_sightings = query_params.getlist("individual_sighting")
        if individual_sightings:
            queryset = queryset.filter(individual_sighting__in=individual_sightings)

        group_sightings = query_params.getlist("group_sighting")
        if individual_sightings:
            queryset = queryset.filter(individual_sighting__group_sighting__in=group_sightings)

        earthranger_ids = query_params.getlist("earthranger_id")
        if earthranger_ids:
            queryset = queryset.filter(
                individual_sighting__group_sighting__earthranger_sighting__earthranger_id__in=earthranger_ids
            )

        earthranger_serials = query_params.getlist("earthranger_serial")
        if earthranger_serials:
            queryset = queryset.filter(
                individual_sighting__group_sighting__earthranger_sighting__earthranger_serial__in=earthranger_serials
            )

        filters = query_params.getlist("filter")
        if filters:
            queryset = queryset.filter(**{k: v for filter in filters for k, v in json.loads(filter).items()})

        return queryset
