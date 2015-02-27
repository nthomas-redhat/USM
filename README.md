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

postgresql93=9.3.6

postgresql93-server=9.3.6

postgresql93-contrib=9.3.6

postgresql93-libs=9.3.6

postgresql93-devel=9.3.6

psycopg2=2.6(This needs to installed after postgress installation)


SETUP
------

Initialize the DB
-----------------
Execute /usr/pgsql-9.3/bin/postgresql93-setup initdb

Configure PostgreSQL to accept network connection
-------------------------------------------------
open /var/lib/pgsql/data/pg_hba.conf
Locate: 127.0.0.1/32 and ::1/128 and allow "password" authentication for IPv4 and IPv6 connections. For example

"host    all             all             127.0.0.1/32            password"

"host    all             all             ::1/128                 password"

Enable and start the postgresSQL service
----------------------------------------
systemctl enable postgresql-9.3
systemctl start postgresql-9.3

Create the Database,User and grant privileges
---------------------------------------------
login to postgres  - sudo su - postgres
create database - createdb usm
create user - createuser -P usm
go to the SQL prompt - psql
Grant the db privileges newly created user - GRANT ALL PRIVILEGES ON DATABASE usm TO usm

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
Start the celery service - service celery start

Starting the USM Application
----------------------------
python manage.py runserver <IPAddress>:<PORT>

Access the usm application using -
http://<IPADDRESS>:<PORT>/