from django.db import models


class EB_FG_Permisson(models.Model):
    class Meta:
        managed = False

        default_permissions = ()

        permissions = (('main', 'Access EB FieldGuide'), )
