#!/bin/bash

# Touch the WSGI file so that the website reloads
touch /var/www/markl_pythonanywhere_com_wsgi.py
echo "Website should reload within a minute"