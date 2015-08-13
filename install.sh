#!/bin/bash

set -e

# Package installation

YELLOW='\033[0;33m'
GREEN='\033[0;32m'
NC='\033[0m'

USM_HOME=`pwd`

printf "${GREEN}Installing necessary packages for USM${NC}\n"

set -x

yum -y install python-django python-django-celery python-django-extensions python-django-bash-completion python-django-filter python-paramiko redis python-redis salt-master postgresql postgresql-server postgresql-devel postgresql-libs postgresql-contrib python-psycopg2 python-netaddr python-cpopen python-gevent python-pip python-devel wget tar

pip install djangorestframework psycogreen
pip install celery --upgrade

# Initialize the DB

set +x

printf "${GREEN}Initializing the DB${NC}\n"

set -x

/usr/bin/postgresql-setup initdb

# Configure PostgreSQL to accept network connection

set +x

printf "${GREEN}Configuring PostgreSQL to accept network connection${NC}\n"

set -x

sed -i 's/127.0.0.1\/32 *ident/127.0.0.1\/32            password/g'  /var/lib/pgsql/data/pg_hba.conf
sed -i 's/::1\/128 *ident/::1\/128                 password/g'  /var/lib/pgsql/data/pg_hba.conf

# Enable and start the postgresSQL service

set +x

printf "${GREEN}Enable and start the postgresSQL service${NC}\n"

set -x

systemctl enable postgresql

systemctl start postgresql

# Create the Database,User and grant privileges

set +x

printf "${GREEN}Creating the Database,User and granting privileges${NC}\n"

set -x

sudo su - postgres -c "createdb usm"

sudo su - postgres -c "psql --command=\"CREATE USER usm WITH PASSWORD 'usm'\""

sudo su - postgres -c "psql --command=\"GRANT ALL PRIVILEGES ON DATABASE usm TO usm\""


# Start the salt service

set +x

printf "${GREEN}Starting salt service${NC}\n"

set -x

systemctl enable salt-master

systemctl start salt-master

# Setup the USM App

set +x

printf "${GREEN}Setting Up USM app${NC}\n"

set -x

mkdir /var/log/usm

cd $USM_HOME

python manage.py makemigrations

python manage.py migrate

set +x

printf "${GREEN}Please Enter Details for USM super-user creation${NC}\n"

set -x

python manage.py createsuperuser


# Celery setup

set +x

printf "${GREEN}Setting up Celery${NC}\n"

set -x

systemctl enable redis

systemctl start redis

sed -i 's|^CELERYD_CHDIR=.*|'CELERYD_CHDIR=\""$USM_HOME"\"'|g' $USM_HOME/celery/default/celeryd

sed -i 's|^DJANGO_PROJECT_DIR=.*|'DJANGO_PROJECT_DIR=\""$USM_HOME"\"'|g' $USM_HOME/celery/default/celeryd

yes |cp $USM_HOME/celery/default/celeryd /etc/default

yes |cp $USM_HOME/celery/init.d/celeryd /etc/init.d

mkdir -p -m 2755 /var/log/celery

service celeryd start

# Salt setup

set +x

printf "${GREEN}Setting up salt${NC}\n"

set -x

yes |cp $USM_HOME/usm_wrappers/setup-minion.sh.template $USM_HOME

mkdir /srv/salt

yes |cp $USM_HOME/usm_wrappers/*.sls /srv/salt

set +x

while true; do
    read -p "Do you wish to install USM-UI [Y/N]:" yn
    case $yn in
        [YyNn]* ) break;;
        * ) echo "Please answer Y or N.";;
    esac
done

if [ $yn = "Y" -o $yn = "y" ]
then
    printf "${GREEN}Downloading and installing usm-client...${NC}\n"
    set -x
    wget http://github.com/kmkanagaraj/usm-client/releases/download/0.0.1/usm-client-0.0.1.tar.gz
    mkdir static
    tar -xzf usm-client-0.0.1.tar.gz -C static/

    set +x
    printf "${YELLOW}Please Make Suitable Firewall settings by unblocking 4505-4506 ports for communication with salt and your HTTP port used for USM....${NC}\n"

    printf "${GREEN}You Can start the USM application by running following command in $USM_HOME dir\nCommand: python manage.py runserver IPAddress:PORT${NC}\n"

    printf "${GREEN}Access the application using http://IPADDRESS:PORT/static/index.html${NC}\n"
else
    set +x

    printf "${YELLOW}Please Make Suitable Firewall settings by unblocking 4505-4506 ports for communication with salt and your HTTP port used for USM....${NC}\n"

    printf "${GREEN}You Can start the USM application by running following command in $USM_HOME dir\nCommand: python manage.py runserver IPAddress:PORT${NC}\n"

    printf "${GREEN}Access the application using http://IPADDRESS:PORT/api/v1${NC}\n"
fi
