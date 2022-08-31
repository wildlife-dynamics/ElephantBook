import django_tables2 as tables

from .models import Assignment


class Assignment_Table(tables.Table):
    id = tables.LinkColumn("eb_anno:assignment view", args=[tables.A("id")])

    class Meta:
        model = Assignment
        template_name = "django_tables2/bootstrap-responsive.html"
        fields = ("id", "annotation_target", "users", "completed", "needs_review")
