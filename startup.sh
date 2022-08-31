#!/bin/sh

if [ "$DATABASE" = "postgres" ]; then
    until python -c "import psycopg2; psycopg2.connect(\"host=$SQL_HOST dbname=$SQL_DATABASE user=$SQL_USER password=$SQL_PASSWORD port=$SQL_PORT \")"; do
        sleep 1
    done
fi

python manage.py makemigrations
python manage.py migrate
python manage.py collectstatic --noinput

exec "$@"
