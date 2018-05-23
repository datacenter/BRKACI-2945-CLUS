#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )/../"
source $SCRIPT_DIR/build/env.sh
TMP_DIR="/tmp/appbuild/"

self=$0
docker_image=""
intro_video=""
private_key=""
enable_proxy="0"
relax_build_checks="0"

function log() {
    ts=`date '+%Y-%m-%dT%H:%M:%S'`
    echo "$ts $@"
}

# ensure build environment has all required tools to perform build
function check_build_tools() {
    log "checking environement dependencies"
    req=(
        "docker" 
        "zip"
        "git"
        "pip"
    )
    for r in "${req[@]}"
    do
        IFS=":" read -r -a split <<< "$r"
        p=${split[0]}
        v=${split[1]}
        if [ ! `which $p` ] ; then 
            echo "" >&2
            echo "requirement '$p' not installed, aborting build" >&2
            echo "" >&2
            exit 1
        fi
        # check version if provided (enforce exact version not minimum version)
        if [ "$v" ] ; then
            version=`$p -v`
            if [ ! "$version" == "$v" ] ; then
                if [ "$relax_build_checks" == "1" ] ; then 
                    log "'$p' version '$version', expected '$v', continuing anyways"
                else
                    echo "" >&2
                    echo "incompatible '$p' version '$version', expected '$v', aborting build" >&2
                    echo "" >&2
                    exit 1
                fi
            fi
        fi
    done
    # ensure user has installed packager cisco-aci-app-tools
    if [ ! `pip freeze 2> /dev/null | egrep "cisco-aci-app-tools" ` ] ; then
        echo "" >&2
        echo "Missing required python dependency 'cisco-aci-app-tools', aborting build" >&2
        echo "You can install via:" >&2
        echo "  pip install build/app_package/cisco_aci_app_tools-1.1_min.tar.gz" >&2
        echo "" >&2
        exit 1
    fi
}

# build aci app
function build_app() {
    set -e
    log "building application $VENDOR_ID/$APP_ID"
    
    # create workspace directory, setup required app-mode directories, and copy over required files
    log "building workspace/copying files to $TMP_DIR/$APP_ID"
    rm -rf $TMP_DIR/$APP_ID
    rm -rf $TMP_DIR/$APP_ID.build
    mkdir -p $TMP_DIR/$APP_ID/UIAssets
    mkdir -p $TMP_DIR/$APP_ID/Service
    mkdir -p $TMP_DIR/$APP_ID/Image
    mkdir -p $TMP_DIR/$APP_ID/Legal
    mkdir -p $TMP_DIR/$APP_ID/Media/Snapshots
    mkdir -p $TMP_DIR/$APP_ID/Media/Readme
    mkdir -p $TMP_DIR/$APP_ID/Media/License
    mkdir -p $TMP_DIR/$APP_ID.build
    
    # copy source code to service
    cp -rp ./Service/* $TMP_DIR/$APP_ID/Service/
    cp -p ./app.json $TMP_DIR/$APP_ID/

    # create media and legal files
    # (note, snapshots are required in order for intro_video to be displayed on appcenter
    if [ "$(ls -A ./Legal)" ] ; then 
        cp -p ./Legal/* $TMP_DIR/$APP_ID/Legal/
    fi
    if [ "$(ls -A ./Media/Snapshots)" ] ; then 
        cp -p ./Media/Snapshots/* $TMP_DIR/$APP_ID/Media/Snapshots/
    fi
    if [ "$(ls -A ./Media/Readme)" ] ; then 
        cp -p ./Media/Readme/* $TMP_DIR/$APP_ID/Media/Readme/
    fi
    if [ "$(ls -A ./Media/License)" ] ; then 
        cp -p ./Media/License/* $TMP_DIR/$APP_ID/Media/License/
    fi

    if [ "$intro_video" ] ; then
        log "adding intro video $intro_video"
        mkdir -p $TMP_DIR/$APP_ID/Media/IntroVideo
        cp $intro_video $TMP_DIR/$APP_ID/Media/IntroVideo/IntroVideo.mp4
        chmod 777 $TMP_DIR/$APP_ID/Media/IntroVideo/IntroVideo.mp4
    elif [ -f ./Media/IntroVideo/IntroVideo.mp4 ] ; then 
        log "adding default intro video"
        mkdir -p $TMP_DIR/$APP_ID/Media/IntroVideo
        cp ./Media/IntroVideo/IntroVideo.mp4 $TMP_DIR/$APP_ID/Media/IntroVideo/IntroVideo.mp4
        chmod 777 $TMP_DIR/$APP_ID/Media/IntroVideo/IntroVideo.mp4
    fi

    # static UIAssets
    if [ "$(ls -A ./UIAssets)" ] ; then
        cp -rp ./UIAssets/* $TMP_DIR/$APP_ID/UIAssets/
    fi

    # build docker container
    if [ "$docker_image" ] ; then
        log "saving docker container image to application"
        cp $docker_image > $TMP_DIR/$APP_ID/Image/aci_appcenter_docker_image.tgz
    else
        log "building container"
        docker_name=`echo "aci/$APP_ID:$APP_VERSION" | tr '[:upper:]' '[:lower:]'`
        if [ "$enable_proxy" == "1" ] ; then
            ba=""
            if [ "$https_proxy" ] ; then ba="$ba --build-arg https_proxy=$https_proxy" ; fi
            if [ "$http_proxy" ] ; then ba="$ba --build-arg http_proxy=$http_proxy" ; fi
            if [ "$no_proxy" ] ; then ba="$ba --build-arg no_proxy=$no_proxy" ; fi
            log "cmd: docker build -t $docker_name $ba --build-arg APP_MODE=1 ./"
            docker build -t $docker_name $ba --build-arg APP_MODE=1 ./build/
        else
            log "cmd: docker build -t $docker_name --build-arg APP_MODE=1 ./"
            docker build -t $docker_name --build-arg APP_MODE=1 ./build/
        fi
        log "saving docker container image to application"
        docker save $docker_name | gzip -c > $TMP_DIR/$APP_ID/Image/aci_appcenter_docker_image.tgz
    fi

    # execute packager
    log "packaging application"
    tar -zxf ./build/app_package/cisco_aci_app_tools-1.1_min.tar.gz -C $TMP_DIR/$APP_ID.build/ 
    if [ "$private_key" ] ; then
        python $TMP_DIR/$APP_ID.build/cisco_aci_app_tools-1.1_min/tools/aci_app_packager.py -f $TMP_DIR/$APP_ID -p $private_key
    else
        python $TMP_DIR/$APP_ID.build/cisco_aci_app_tools-1.1_min/tools/aci_app_packager.py -f $TMP_DIR/$APP_ID
    fi

    # cleanup
    rm -rf $TMP_DIR/$APP_ID.build
    rm -rf $TMP_DIR/$APP_ID
   
    log "build complete: `ls -a $TMP_DIR/*.aci`"

    set +e
}

# help options
function display_help() {
    echo ""
    echo "Help documentation for $self"
    echo "    -i docker image to bundled into app (.tgz format)"
    echo "    -v path to intro video (.mp4 format)"
    echo "    -p private key uses for signing app"
    echo "    -x send local environment proxy settings to container during build"
    echo "    -r relax build checks (ensure tools are present but skip version check)"
    echo ""
    exit 0
}


optspec=":i:v:p:hxr"
while getopts "$optspec" optchar; do
  case $optchar in
    i)
        docker_image=$OPTARG
        if [ ! -f $docker_image ] ; then
            echo "" >&2
            echo "docker image '$docker_image' not found, aborting build" >&2
            echo "" >&2
            exit 1 
        fi
        ;;
    v) 
        intro_video=$OPTARG
        if [ ! -f $intro_video ] ; then
            echo "" >&2
            echo "intro video '$intro_video' not found, aborting build" >&2
            echo "" >&2
            exit 1
        fi
        ;;
    p)
        private_key=$OPTARG
        if [ ! -f $private_key ] ; then
            echo "" >&2
            echo "private key '$private_key' not found, aborting build" >&2
            echo "" >&2
            exit 1
        fi
        ;;
    x)
        enable_proxy="1"
        ;;
    r)
        relax_build_checks="1"
        ;;
    h)
        display_help
        exit 0
        ;;
    :)
        echo "Option -$OPTARG requires an argument." >&2
        exit 1
        ;;
    \?)
        echo "Invalid option: \"-$OPTARG\"" >&2
        exit 1
        ;;
  esac
done

# check depedencies first and then execute build
check_build_tools
build_app

