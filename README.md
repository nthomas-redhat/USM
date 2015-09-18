USM is an application that manages Ceph and Gluster

REQUIREMENTS
------------

python >= 2.7

django-celery==3.1.16

django-extensions==1.5.0

django-filter==0.9.2

djangorestframework==3.0.5

celery==3.1.17

Django==1.7.5

paramiko=1.15.1

redis = 2.8.18

python-redis=2.10.3

salt-master =2014.7.1

postgresql=9.3.6

postgresql-server=9.3.6

postgresql-contrib=9.3.6

postgresql-libs=9.3.6

postgresql-devel=9.3.6

psycopg2=2.6(This needs to installed after postgress installation)

python-netaddr=0.7.12

python-cpopen=1.3

gevent==1.0.1

psycogreen==1.0

NOTE: few of the packages like djangorestframework, psycogreen are not available through yum,
they have to be installed using pip tool.

SETUP
------

Initialize the DB
-----------------
Execute /usr/bin/postgresql-setup initdb

Configure PostgreSQL to accept network connection
-------------------------------------------------
open /var/lib/pgsql/data/pg_hba.conf
Locate: 127.0.0.1/32 and ::1/128 and allow "password" authentication for IPv4 and IPv6 connections. For example

"host    all             all             127.0.0.1/32            password"

"host    all             all             ::1/128                 password"

Enable and start the postgresSQL service
----------------------------------------
systemctl enable postgresql

systemctl start postgresql

Create the Database,User and grant privileges
---------------------------------------------
login to postgres  - sudo su - postgres

create database - createdb usm

create user - createuser -P usm

go to the SQL prompt - psql

Grant the db privileges newly created user - GRANT ALL PRIVILEGES ON DATABASE usm TO usm;

Start the salt service
----------------------
systemctl enable salt-master

systemctl start salt-master

Setup the USM App
-----------------
clone the Repo - https://github.com/nthomas-redhat/USM

create the logs directory - mkdir /var/log/usm

create and migrate the DB -

python manage.py makemigrations

python manage.py migrate

Create the superuser -

python manage.py createsuperuser

Firewall configuration
----------------------
Make sure all the required ports are unblocked - ports 4505-4506/tcp for salt and the one usm app is listening on

firewall-cmd --permanent --zone=FedoraWorkstation or FedoraServer --add-port=4505-4506/tcp  FOR SALT

firewall-cmd --permanent --zone=FedoraWorkstation or FedoraServer --add-port=<HTTP PORT>/tcp  FOR HTTP

Celery Setup
------------
Enable and start redis -

systemctl enable redis

systemctl start redis

Configure the celery environment -

Open celery/default/celeryd and update below variables to point to USM HOME DIRECTORY

CELERYD_CHDIR="USM_HOME_DIRECTORY"

DJANGO_PROJECT_DIR="USM_HOME_DIRECTORY"

Copy the init and config files -

cp celery/default/celeryd /etc/default

cp celery/init.d/celeryd /etc/init.d

Create the logs directory - mkdir -p -m 2755 /var/log/celery

Start the celery service - service celeryd start

Salt Setup
----------
copy the template file -

cp $USM_HOME/usm_wrappers/setup-minion.sh.template $USM_HOME

copy the sls files -

cp $USM_HOME/usm_wrappers/*.sls /srv/salt

Starting the USM Application
----------------------------
python manage.py runserver IPAddress:PORT

Access the usm application using -

http://IPADDRESS:PORT/

Install Script
--------------

Alternatively Setup on a fresh machine can be done using install.sh script
available in this repo. This script takes care of:
* Installing the necessary dependent packages.
* Setting up the Database
* Setting up the USM app
* Setting up celery, salt and redis.

This script has been tested on Fedora-22.