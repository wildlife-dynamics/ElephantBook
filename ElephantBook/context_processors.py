from django.conf import settings


def er_endpoints(request):
    return {
        "ER_MAIN": settings.ER_MAIN,
        "ER_ADMIN": settings.ER_ADMIN,
    }
