from django.contrib import admin

from .models import Bbox_ML, Embedding, Photo_ML

admin.site.register(Photo_ML)
admin.site.register(Bbox_ML)
admin.site.register(Embedding)
