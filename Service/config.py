import os, logging

# specify mongo uri
#   mongodb://[username:password@]host1[:port1][,host2[:port2],\
#    ...[,hostN[:portN]]][/[database][?options]]
#MONGO_URI = os.environ.get('MONGO_URI',
#    "mongodb://localhost:27017/devdb?connectTimeoutMS=5000&socketTimeoutMS=20000&serverSelectionTimeoutMS=5000")
MONGO_HOST = os.environ.get("MONGO_HOST", "localhost")
MONGO_PORT = int(os.environ.get("MONGO_PORT", 27017))
MONGO_DBNAME = os.environ.get("MONGO_DBNAME","devdb")
MONGO_SERVER_SELECTION_TIMEOUT_MS = 5000
MONGO_CONNECT_TIMEOUT_MS = 5000
MONGO_SOCKET_TIMEOUT_MS = 20000

# enable application debugging (ensure debugging is disabled on production app)
DEBUG = bool(int(os.environ.get("DEBUG", 1)))

# disable pretty print by default to help with large repsonses
JSONIFY_PRETTYPRINT_REGULAR = bool(int(
                            os.environ.get("JSONIFY_PRETTYPRINT_REGULAR",0)))

# logging options
LOG_DIR = os.environ.get("LOG_DIR", "/home/app/log")
LOG_LEVEL = int(os.environ.get("LOG_LEVEL", logging.DEBUG))
LOG_ROTATE = bool(int(os.environ.get("LOG_ROTATE", 0)))
LOG_ROTATE_SIZE = os.environ.get("LOG_ROTATE_SIZE", 26214400)
LOG_ROTATE_COUNT = os.environ.get("LOG_ROTATE_COUNT", 3)

# application running as an app on aci apic (ensure started file matches
# start.sh settings)
APIC_HOSTNAME = os.environ.get("APIC_HOSTNAME", "172.17.0.1")
APIC_USERNAME = os.environ.get("APIC_USERNAME", "admin")
APIC_PASSWORD = os.environ.get("APIC_PASSWORD", "cisco")
APIC_CERT_MODE= bool(int(os.environ.get("APIC_CERT_MODE", 1)))
APIC_APP_USER = os.environ.get("APIC_APP_USER", "Cisco_CLUS")
PRIVATE_CERT = os.environ.get("PRIVATE_CERT","/home/app/credentials/plugin.key")

