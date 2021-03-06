#!/bin/bash

# startup script for app_mode on APIC or standalone application
# this script is responsible for starting up following background services:
#   1) apache2
#   2) cron     (required for logrotate)
#   3) mongo
#

# start.sh will be executed from either base of project or from ./bash directory
# force it to always be base of project
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )/"
SCRIPT_DIR=`echo $SCRIPT_DIR | sed -e 's/bash\/$//'`

# this variables should already be set within container but creating defaults 
# just in case
APP_MODE=${APP_MODE:-0}
APP_DIR=${APP_DIR:-/home/app}
DATA_DIR=${DATA_DIR:-/home/app/data}
LOG_DIR=${LOG_DIR:-/home/app/log}
SRC_DIR="$APP_DIR/src/Service"
CRED_DIR="$APP_DIR/credentials"
PRIVATE_CONFIG="$APP_DIR/config.py"
LOG_FILE="$LOG_DIR/start.log"
STARTED_FILE="$APP_DIR/.started"
STATUS_FILE="$APP_DIR/.status"
MONGO_CONFIG="/etc/mongod.conf"
MONGO_MAX_WAIT_COUNT=50
APIC_HOSTNAME=""   # discovered at run in APP_MODE

# required services to start
ALL_SERVICES=(
    "cron" 
    "apache2"
    "mongodb"
)

# python logging levels integers for reference
LOGGING_LEVEL_DEBUG=10
LOGGING_LEVEL_INF0=20
LOGGING_LEVEL_WARN=30
LOGGING_LEVEL_ERROR=40
LOGGING_LEVEL_CRITICAL=50

# log message to stdout and to logfile
function log(){
    ts=`date '+%Y-%m-%dT%H:%M:%S'`
    echo "$ts $@"
    if [ "$LOG_FILE" ] ; then
        echo "$ts $@" >> $LOG_FILE 2> /dev/null
    fi
}

# update value in status file 
# this is a single line file with a description of the current startup status
function set_status(){
    ts=`date '+%Y-%m-%dT%H:%M:%S'`
    log "status: $1"
    if [ "$STATUS_FILE" ] ; then
        echo "($ts) $1" > $STATUS_FILE 2> /dev/null
    fi
}

# force script to exit after timeout
function exit_script(){
    local timeout=10
    log "exiting in $timeout seconds"
    sleep $timeout
    log "exit"
    exit 1
}

# required dictories for logging and database datastore
function setup_directories() {
    set_status "setting up backend directories"

    # if base directories do not exists, then something has gone terribly wrong...
    critical=( $APP_DIR $LOG_DIR $DATA_DIR $SRC_DIR )
    for d in "${critical[@]}" ; do
        if [ ! -d $d ] ; then
            set_status "error: required directory $d not found"
            exit_script
        fi
        log "directory $d found"
    done

    if [ ! -d $DATA_DIR/snapshots ] ; then
        log "create $DATA_DIR/snapshots"
        mkdir -p $DATA_DIR/snapshots
        chown www-data:www-data $DATA_DIR/snapshots -R
    fi
    if [ ! -d $DATA_DIR/db ] ; then
        log "create $DATA_DIR/db"
        mkdir -p $DATA_DIR/db
        chown mongodb:mongodb $DATA_DIR/db -R
    fi
    if [ ! -d $LOG_DIR/mongo ] ; then
        log "create $LOG_DIR/mongo"
        mkdir -p $LOG_DIR/mongo/
        chown mongodb:mongodb $LOG_DIR/mongo/ -R
    fi
    if [ ! -d $LOG_DIR/apache2 ] ; then
        log "create $LOG_DIR/apache2"
        mkdir -p $LOG_DIR/apache2/ 
        chown www-data:www-data $LOG_DIR/apache2 -R
    fi
    # backend scripts run under www-data user and write directly to LOG_DIR
    chown www-data:www-data $LOG_DIR/*.log
    chmod 777 $LOG_DIR/*.log
    chmod 777 $LOG_DIR
}

#  check if provided service is running.  return 1 (error) if not running
function service_is_running(){
    # if no service provided then return error
    local service=$1
    if [ ! "$service" ] ; then return 1 ; fi
    local count=`ps -ef | egrep $service | egrep -v grep | wc -l`
    if [ "$count" -ge "1" ] ; then
        log "service $service is running"
        return 0
    else
        log "service $service is NOT running"
        return 1
    fi
}

# start a particular service and return error code on failure
function start_service(){
    local service=$1
    local sleep_time=5
    if [ ! "$service" ] ; then return 1 ; fi
    set_status "starting service $service"
    log `service $service start 2>&1`
    # wait a few seconds before checking service is running
    log "pause $sleep_time seconds before checking service status"
    sleep $sleep_time
    if ! service_is_running $service ; then
        set_status "failed to start service $service"
        return 1
    fi
    # for mongo, ensure we can connect to the db
    if [ "$service" == "mongodb" ] ; then
        if ! mongodb_accept_connections ; then
            return 1
        fi
    fi
    return 0
}

# start required backend services and check status to ensure successfully started
function start_all_services(){
    set_status "starting all services"
    for s in "${ALL_SERVICES[@]}" ; do
        if ! start_service $s ; then
            if [ "$s" == "mongodb" ] ; then
                if ! mongodb_reconfigure_and_restart ; then exit_script ; fi
            else
                exit_script
            fi 
        else
            log "successfully started service $s"
        fi
    done
}

# multiple problems with mongodb in app mode and interaction with glusterfs
# if mongo fails to start use the below recovery method to move mongo off of
# glusterfs.  Note, all previous database data is lost when this occurs AND new
# data is not persisted if app is moved to different APIC 
function mongodb_reconfigure_and_restart(){
    set_status "attempting mongodb remediation"
    if [ "$APP_MODE" == "0" ] ; then
        log "recovery only supported in app mode, aborting..."
        return 1        
    fi
    log `service mongodb force-stop 2>&1`
    DATA_DIR="/data/"
    log `rm -rf $DATA_DIR`
    mkdir -p $DATA_DIR
    chmod 777 $DATA_DIR
    setup_directories
    log `sed -i '/  dbPath:/c\  dbPath: \/data\/db' $MONGO_CONFIG 2>&1`
    start_service "mongodb"
    return "$?"
}

# ensure mongo db is accepting new connections.  It may take a few minutes on 
# slow filesystems when allocating db chunks or rebuilding from journaling
function mongodb_accept_connections(){
    local wait_time=3
    local i="0"
    local cmd="cd $SCRIPT_DIR ; python -m app.subscriber --check_db"
    while [ $i -lt "$MONGO_MAX_WAIT_COUNT" ] ; do
        set_status "checking mongodb is accepting connections $i/$MONGO_MAX_WAIT_COUNT"
        log "command: $cmd"
        if su - -s /bin/bash www-data -c "$cmd" ; then
            log "successfully connected to database"
            return 0
        else
            log "failed to connected to database"
        fi
        log "mongodb is not ready, sleeping for $wait_time seconds"
        sleep $wait_time
        i=$[$i+1]
    done 
    set_status "failed to connect to mongodb after $i attempts"
    return 1
}

# set global APIC_HOSTNAME to default IP when in APP_MODE
function get_apic_hostname() {
    if [ "$APP_MODE" == "1" ] ; then
        log "checking default route for APIC hostname"
        out=`ip route | egrep -o "default via [0-9\.]+" | awk '{print $3}' 2>&1`
        if [ "$?" == "0" ] ; then
            APIC_HOSTNAME=$out
            log "setting APIC_HOSTNAME to $APIC_HOSTNAME"
            return 0
        else 
            log "failed to execute command: $out" 
        fi 
    else
        log "skipping get_apic_hostname, not in APP mode"
    fi
    return 1
}

# setup app required environment variables
function create_app_config_file() {
    set_status "creating app config_file"

    local instance_config="$SRC_DIR/instance"
    local config_file="$instance_config/config.py"
    if [ ! -d $instance_config ] ; then 
        mkdir -p $instance_config
    fi
    
    # set APIC_HOSTNAME variable if found
    
    # app mode specific settings
    if [ "$APP_MODE" == "1" ] ; then
        echo "" > $config_file
        echo "LOG_DIR=\"$LOG_DIR/\"" >> $config_file
        echo "LOG_ROTATE=0" >> $config_file
        echo "APIC_CERT_MODE=1" >> $config_file
        echo "APIC_APP_USER=\"Cisco_CLUS\"" >> $config_file
        echo "PRIVATE_CERT=\"$CRED_DIR/plugin.key\"" >> $config_file
        if get_apic_hostname  ; then
            log "setting APIC hostname in $config_file: $APIC_HOSTNAME"
            echo "APIC_HOSTNAME=\"$APIC_HOSTNAME\"" >> $config_file
        fi
    fi
    chmod 755 $config_file

}


# main container startup
function main(){
    log "======================================================================"
    set_status "restarting"
    log "======================================================================"
    log `rm -f $STARTED_FILE 2>&1`

    # setup required directories with proper write access and custom app config
    setup_directories
    start_all_services
    create_app_config_file

    log `touch $STARTED_FILE 2>&1`
    set_status "running"

    # run subscriber forever - if subscriber fails the start.sh will fail
    local cmd="cd $SCRIPT_DIR ; python -m app.subscriber"
    log "command: $cmd"
    su - -s /bin/bash www-data -c "$cmd" 
    
    set_status "error: subscription unexpectedly closed"
    exit_script
}


# execute main 
main
