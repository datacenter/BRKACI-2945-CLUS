# BRKACI-2945-CLUS Demo Application

This is an example ACI application presented during CiscoLive BRKACI-2945. This 
app will display all endpoints learned for a provided prefix. In addition, the 
app can resolve dns for each IP using the configured dnsProv objects on the APIC.

This app can easily be extended to provide additional functionality.  To learn
more, checkout the the session on the 
[CiscoLive On-Demand Library](https://www.ciscolive.com/global/on-demand-library/)

## Getting Started

The first step is to clone the project:
```
$ git clone git@github.com:datacenter/BRKACI-2945-CLUS.git
Cloning into 'BRKACI-2945-CLUS'...
remote: Counting objects: 89, done.
remote: Compressing objects: 100% (77/77), done.
remote: Total 89 (delta 3), reused 89 (delta 3), pack-reused 0
Receiving objects: 100% (89/89), 2.06 MiB | 45.00 KiB/s, done.
Resolving deltas: 100% (3/3), done.

$ cd BRKACI-2945-CLUS/
BRKACI-2945-CLUS$
```

To build the app you need to first create the docker container and save it
into the Image/ folder. This will required [Docker](https://www.docker.com) 
installed on your development machine.  Then execute the packager script to run 
the app validation and bundle into the .aci file. There is a bash build script 
to help automate this process.

Before executing the build script, install the packager dependencies via `pip`:

> **NOTE** it a good idea to activate a virtual environment before installing
> python dependencies. Checkout [virtualenv](https://virtualenv.pypa.io/en/stable/)
> and [pyenv](http://docs.python-guide.org/en/latest/dev/virtualenvs/) for more
> info on setting up virtual environments.

```

BRKACI-2945-CLUS$ pyenv activate clus

(clus) BRKACI-2945-CLUS$ pip install build/app_package/cisco_aci_app_tools-1.1_min.tar.gz
Processing ./build/app_package/cisco_aci_app_tools-1.1_min.tar.gz
...
<snip>
...
Installing collected packages: Werkzeug, click, MarkupSafe, Jinja2, itsdangerous, flask, pycrypto, decorator, six, validators, python-magic, cisco-aci-app-tools
Successfully installed Jinja2-2.10 MarkupSafe-1.0 Werkzeug-0.14.1 cisco-aci-app-tools-1.1 click-6.7 decorator-4.3.0 flask-1.0.2 itsdangerous-0.24 pycrypto-2.6.1 python-magic-0.4.15 six-1.11.0 validators-0.12.1
```

Now that the dependencies are met, execute the build script to build the app

```
BRKACI-2945-CLUS$ ./build/build_app.sh
2018-05-25T10:01:42 checking environment dependencies
2018-05-25T10:01:43 building application Cisco/CLUS
2018-05-25T10:01:43 building workspace/copying files to /tmp/appbuild//CLUS
2018-05-25T10:01:43 adding default intro video
2018-05-25T10:01:43 building container
2018-05-25T10:01:43 cmd: docker build -t aci/clus:1.0 --build-arg APP_MODE=1 ./
...
2018-05-25T10:01:43 saving docker container image to application
2018-05-25T10:02:38 packaging application
...
2018-05-25T10:02:54 build complete: /tmp/appbuild//Cisco-CLUS-1.0.aci
```
