#!/bin/bash -xe

# This script will be run by OpenStack CI before unit tests are run,
# it sets up the test system as needed.
# Developers should setup their test systems in a similar way.

# This setup needs to be run as a user that can run sudo.

# The root password for the MySQL database; pass it in via
# MYSQL_ROOT_PW.
DB_ROOT_PW=${MYSQL_ROOT_PW:-insecure_slave}

# This user and its password are used by the tests, if you change it,
# your tests might fail.
DB_USER=openstack_citest
DB_PW=openstack_citest

function set_conf_line {
    # parameters: file regex value
    # check if the regex occurs in the file
    # If so, replace with the value.
    # If not, append the value to the end of the file.
    sudo sh -c "grep -q -e '$2' $1 && \
            sed -i 's|$2|$3|g' $1 || \
            echo '$3' >> $1"
}

if $(egrep -q "^.*(centos:centos:|cloudlinux:cloudlinux:|redhat:enterprise_linux:)[78].*$" /etc/*release); then
    # mysql needs to be started on centos/rhel
    sudo systemctl restart mariadb.service

    # postgres setup for centos
    # make sure to use scram-sha-256 instead of md5 for fips!
    sudo postgresql-setup --initdb
    PG_CONF=/var/lib/pgsql/data/postgresql.conf
    set_conf_line $PG_CONF '^password_encryption =.*' 'password_encryption = scram-sha-256'

    PG_HBA=/var/lib/pgsql/data/pg_hba.conf
    set_conf_line $PG_HBA '^local[ \t]*all[ \t]*all.*' 'local all all peer'
    set_conf_line $PG_HBA '^host[ \t]*all[ \t]*all[ \t]*127.0.0.1\/32.*' 'host all all 127.0.0.1/32 scram-sha-256'
    set_conf_line $PG_HBA '^host[ \t]*all[ \t]*all[ \t]*::1\/128.*' 'host all all ::1/128 scram-sha-256'

    sudo systemctl restart postgresql.service
fi

sudo -H mysqladmin -u root password $DB_ROOT_PW

# It's best practice to remove anonymous users from the database.  If
# a anonymous user exists, then it matches first for connections and
# other connections from that host will not work.
sudo -H mysql -u root -p$DB_ROOT_PW -h localhost -e "
    DELETE FROM mysql.user WHERE User='';
    FLUSH PRIVILEGES;
    CREATE USER '$DB_USER'@'%' IDENTIFIED BY '$DB_PW';
    GRANT ALL PRIVILEGES ON *.* TO '$DB_USER'@'%' WITH GRANT OPTION;"

# Now create our database.
mysql -u $DB_USER -p$DB_PW -h 127.0.0.1 -e "
    SET default_storage_engine=MYISAM;
    DROP DATABASE IF EXISTS openstack_citest;
    CREATE DATABASE openstack_citest CHARACTER SET utf8;"

# Same for PostgreSQL
# The root password for the PostgreSQL database; pass it in via
# POSTGRES_ROOT_PW.
DB_ROOT_PW=${POSTGRES_ROOT_PW:-insecure_slave}

# Setup user
root_roles=$(sudo -H -u postgres psql -t -c "
   SELECT 'HERE' from pg_roles where rolname='$DB_USER'")
if [[ ${root_roles} == *HERE ]];then
    sudo -H -u postgres psql -c "ALTER ROLE $DB_USER WITH SUPERUSER LOGIN PASSWORD '$DB_PW'"
else
    sudo -H -u postgres psql -c "CREATE ROLE $DB_USER WITH SUPERUSER LOGIN PASSWORD '$DB_PW'"
fi

# Store password for tests
cat << EOF > $HOME/.pgpass
*:*:*:$DB_USER:$DB_PW
EOF
chmod 0600 $HOME/.pgpass

# Now create our database
psql -h 127.0.0.1 -U $DB_USER -d template1 -c "DROP DATABASE IF EXISTS openstack_citest"
createdb -h 127.0.0.1 -U $DB_USER -l C -T template0 -E utf8 openstack_citest
