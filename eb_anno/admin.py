from django.contrib import admin

from .models import (
    Annotation_Target,
    Annotation_Target_Photo,
    Assignment,
    Assignment_Bounding_Box,
)

admin.site.register(Annotation_Target)
admin.site.register(Annotation_Target_Photo)
admin.site.register(Assignment)
admin.site.register(Assignment_Bounding_Box)
