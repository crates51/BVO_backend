#!/bin/sh

if [ -z "$OLT_DOMAIN" ]; then
    echo "OLT_DOMAIN var is missing from environment"
    export OLT_DOMAIN='olt.next-gen.ro'
fi
sleep 5
python manage.py db upgrade

if [ ! -f /etc/letsencrypt/live/$OLT_DOMAIN/fullchain.pem ] || [ ! -f /etc/letsencrypt/live/$OLT_DOMAIN/privkey.pem ]; then
    echo "Missing certificate files from /etc/letsencrypt/live/$OLT_DOMAIN/. Gonna start plain http"
    exec uwsgi --ini uwsgi.ini --http 0.0.0.0:6001 --thunder-lock
else
    exec uwsgi --ini uwsgi.ini --https 0.0.0.0:6001,/etc/letsencrypt/live/$OLT_DOMAIN/fullchain.pem,/etc/letsencrypt/live/$OLT_DOMAIN/privkey.pem --thunder-lock
fi

