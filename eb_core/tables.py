import django_tables2 as tables

from .models import (
    EarthRanger_Sighting,
    Group_Sighting,
    Individual,
    Individual_Sighting,
    Subgroup_Sighting,
)


class Float3FColumn(tables.Column):
    def render(self, value):
        if isinstance(value, float):
            return f"{value:.3f}"
        return value


class Group_Sighting_Table(tables.Table):
    id = tables.LinkColumn("group sighting view", args=[tables.A("id")])
    lat = Float3FColumn()
    lon = Float3FColumn()

    class Meta:
        model = Group_Sighting
        template_name = "django_tables2/bootstrap-responsive.html"
        fields = ("id", "lat", "lon", "datetime")


class EarthRanger_Sighting_Table(Group_Sighting_Table):
    id = tables.LinkColumn("earthranger sighting view", args=[tables.A("earthranger_serial")])
    lat = Float3FColumn()
    lon = Float3FColumn()

    class Meta:
        model = EarthRanger_Sighting
        template_name = "django_tables2/bootstrap-responsive.html"
        fields = ("id", "earthranger_serial", "datetime", "lat", "lon", "earthranger_id")

    def render_earthranger_serial(self, value):
        return str(value)


class Individual_Sighting_Table(tables.Table):
    id = tables.LinkColumn("individual sighting view", args=[tables.A("id")])
    group_sighting = tables.LinkColumn("group sighting view", args=[tables.A("group_sighting_id")])
    individual = tables.LinkColumn("individual view", args=[tables.A("individual_id")])

    class Meta:
        model = Individual_Sighting
        template_name = "django_tables2/bootstrap-responsive.html"
        fields = ("id", "group_sighting", "individual", "completed", "expert_reviewed", "unidentifiable")


class Individual_Table(tables.Table):
    id = tables.LinkColumn("individual view", args=[tables.A("id")])

    class Meta:
        model = Individual
        template_name = "django_tables2/bootstrap-responsive.html"
        fields = ("id", "name")


class Subgroup_Sighting_Table(tables.Table):
    id = tables.LinkColumn("subgroup sighting view", args=[tables.A("id")])
    group_sighting = tables.LinkColumn("group sighting view", args=[tables.A("group_sighting_id")])

    class Meta:
        model = Subgroup_Sighting
        template_name = "django_tables2/bootstrap-responsive.html"
        fields = (
            "id",
            "group_sighting",
            "group_sighting__datetime",
            "group_type",
            "individual_sightings",
            "unphotographed_individuals",
        )


class Search_Table(tables.Table):
    rank = tables.Column()
    individual = tables.LinkColumn(
        "individual view", args=[tables.A("individual__id")], order_by=tables.A("individual__id")
    )
    score = Float3FColumn()
    seek_score = Float3FColumn()
    seek_code = tables.Column()
    right_ear_emb_score = Float3FColumn()
    left_ear_emb_score = Float3FColumn()

    class Meta:
        template_name = "django_tables2/bootstrap-responsive.html"
