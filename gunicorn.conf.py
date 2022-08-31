import multiprocessing

wsgi_app = "ElephantBook.wsgi:application"
bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
timeout = 7200
reload = True
accesslog = "/ElephantBook/logs/gunicorn.access.log"
errorlog = "/ElephantBook/logs/gunicorn.error.log"
loglevel = "warning"
