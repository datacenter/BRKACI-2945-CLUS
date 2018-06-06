
import logging, logging.handlers, time, re, sys, traceback, json
from flask import request
from pymongo import IndexModel
from pymongo.errors import (DuplicateKeyError, ServerSelectionTimeoutError)
from pymongo import (ASCENDING, DESCENDING)

# module level logging
logger = logging.getLogger(__name__)

# track app so we don't need to create it multiple times
_g_app = None
def get_app():
    # returns current app
    from . import create_app
    global _g_app
    if _g_app is None: _g_app = create_app("config.py")
    return _g_app

def get_app_config():
    # return config dict from app
    app = get_app()
    if hasattr(app, "config"): return app.config
    return {}

# static queue thresholds and timeouts
SESSION_MAX_TIMEOUT = 120   # apic timeout hardcoded to 90...
SESSION_LOGIN_TIMEOUT = 10  # login should be fast

###############################################################################
#
# common logging formats
#
###############################################################################

def setup_logger(logger, fname="app.log", quiet=False, stdout=False):
    """ setup logger with appropriate logging level and rotate options """

    # quiet all other loggers...
    if quiet:
        old_logger = logging.getLogger()
        old_logger.setLevel(logging.CRITICAL)
        for h in list(old_logger.handlers): old_logger.removeHandler(h)
        old_logger.addHandler(logging.NullHandler())

    app = get_app()
    logger.setLevel(app.config["LOG_LEVEL"])
    try:
        if stdout:
            logger_handler = logging.StreamHandler(sys.stdout)
        elif app.config["LOG_ROTATE"]:
            logger_handler = logging.handlers.RotatingFileHandler(
                "%s/%s"%(app.config["LOG_DIR"],fname),
                maxBytes=app.config["LOG_ROTATE_SIZE"],
                backupCount=app.config["LOG_ROTATE_COUNT"])
        else:
            logger_handler = logging.FileHandler(
                "%s/%s"%(app.config["LOG_DIR"],fname))
    except IOError as e:
        sys.stderr.write("failed to open logger handler: %s, resort stdout\n"%e)
        logger_handler = logging.StreamHandler(sys.stdout)

    fmt ="%(process)d||%(asctime)s.%(msecs).03d||%(levelname)s||%(filename)s"
    fmt+=":(%(lineno)d)||%(message)s"
    logger_handler.setFormatter(logging.Formatter(
        fmt=fmt,
        datefmt="%Z %Y-%m-%d %H:%M:%S")
    )
    # remove previous handlers if present
    for h in list(logger.handlers): logger.removeHandler(h)
    logger.addHandler(logger_handler)
    return logger

###############################################################################
#
# misc/common functions
#
###############################################################################

def pretty_print(js):
    """ try to convert json to pretty-print format """
    try:
        return json.dumps(js, indent=4, separators=(",", ":"), sort_keys=True)
    except Exception as e:
        return "%s" % js

def get_user_data():
    """ returns user provided json or empty dict """
    try:
        if not request.json: return {}
        ret = request.json
        if not isinstance(ret, dict): return {}
        return ret
    except Exception as e: return {}

def get_user_params():
    """ returns dict of user provided params """
    try:
        if not request.args: return {}
        ret = {}
        for k in request.args:
            ret[k] = request.args.get(k)
        return ret
    except Exception as e: return {}

###############################################################################
#
# REST/connectivity functions
#
###############################################################################

def build_query_filters(**kwargs):
    """
        queryTarget=[children|subtree]
        targetSubtreeClass=[mo-class]
        queryTargetFilter=[filter]
        rspSubtree=[no|children|full]
        rspSubtreeInclude=[attr]
        rspPropInclude=[all|naming-only|config-explicit|config-all|oper]
        orderBy=[attr]
    """
    queryTarget         = kwargs.get("queryTarget", None)
    targetSubtreeClass  = kwargs.get("targetSubtreeClass", None)
    queryTargetFilter   = kwargs.get("queryTargetFilter", None)
    rspSubtree          = kwargs.get("rspSubtree", None)
    rspSubtreeInclude   = kwargs.get("rspSubtreeInclude", None)
    rspPropInclude      = kwargs.get("rspPropInclude", None)
    orderBy             = kwargs.get("orderBy", None)
    opts = ""
    if queryTarget is not None:
        opts+= "&query-target=%s" % queryTarget
    if targetSubtreeClass is not None:
        opts+= "&target-subtree-class=%s" % targetSubtreeClass
    if queryTargetFilter is not None:
        opts+= "&query-target-filter=%s" % queryTargetFilter
    if rspSubtree is not None:
        opts+= "&rsp-subtree=%s" % rspSubtree
    if rspSubtreeInclude is not None:
        opts+= "&rsp-subtree-include=%s" % rspSubtreeInclude
    if rspPropInclude is not None:
        opts+= "&rsp-prop-include=%s" % rspPropInclude
    if orderBy is not None:
        opts+= "&order-by=%s" % orderBy

    if len(opts)>0: opts = "?%s" % opts.strip("&")
    return opts

def get(session, url, **kwargs):
    # handle session request and perform basic data validation.  Return
    # None on error

    # default page size handler and timeouts
    page_size = kwargs.get("page_size", 75000)
    timeout = kwargs.get("timeout", SESSION_MAX_TIMEOUT)
    limit = kwargs.get("limit", None)       # max number of returned objects
    page = 0

    url_delim = "?"
    if "?" in url: url_delim="&"

    results = []
    # walk through pages until return count is less than page_size
    while 1:
        turl = "%s%spage-size=%s&page=%s" % (url, url_delim, page_size, page)
        logger.debug("host:%s, timeout:%s, get:%s" % (session.ipaddr,
            timeout,turl))
        tstart = time.time()
        try:
            resp = session.get(turl, timeout=timeout)
        except Exception as e:
            logger.warn("exception occurred in get request: %s" % (
                traceback.format_exc()))
            return None
        logger.debug("response time: %f" % (time.time() - tstart))
        if resp is None or not resp.ok:
            logger.warn("failed to get data: %s" % url)
            return None
        try:
            js = resp.json()
            if "imdata" not in js or "totalCount" not in js:
                logger.warn("failed to parse js reply: %s" % pretty_print(js))
                return None
            results+=js["imdata"]
            logger.debug("results count: %s/%s"%(len(results),js["totalCount"]))
            if len(js["imdata"])<page_size or \
                len(results)>=int(js["totalCount"]):
                logger.debug("all pages received")
                return results
            elif (limit is not None and len(js["imdata"]) >= limit):
                logger.debug("limit(%s) hit or exceeded" % limit)
                return results[0:limit]
            page+= 1
        except ValueError as e:
            logger.warn("failed to decode resp: %s" % resp.text)
            return None
    return None

def get_dn(session, dn, **kwargs):
    # get a single dn.  Note, with advanced queries this may be list as well
    # therefore, if len(results)>1, then original list is returned
    opts = build_query_filters(**kwargs)
    url = "/api/mo/%s.json%s" % (dn,opts)
    results = get(session, url, **kwargs)
    if results is not None:
        if len(results)>0: return results[0]
        else: return {} # empty non-None object implies valid empty response
    return None

def get_class(session, classname, **kwargs):
    # perform class query
    opts = build_query_filters(**kwargs)
    url = "/api/class/%s.json%s" % (classname, opts)
    return get(session, url, **kwargs)

def get_parent_dn(dn):
    # return parent dn for provided dn
    t = dn.split("/")
    t.pop()
    return "/".join(t)

def get_apic_session(subscription_enabled=False):
    """ get_apic_session
        based on app settings, connect to configured apic and return valid
        session object

        Returns None on failure
    """
    from .acitoolkit.acisession import Session
   
    app = get_app() 
    
    apic_cert_mode= app.config["APIC_CERT_MODE"]
    apic_hostname = app.config["APIC_HOSTNAME"]
    apic_username = app.config["APIC_USERNAME"]
    apic_password = app.config["APIC_PASSWORD"]
    apic_app_user = app.config["APIC_APP_USER"]
    private_cert = app.config["PRIVATE_CERT"]

    # ensure apic_hostname is in url form.  If not, assuming https
    if not re.search("^http", apic_hostname.lower()): 
        apic_hostname = "https://%s" % apic_hostname

    # create session object
    logger.debug("attempting to create session on (cert:%r) %s@%s" % (
        apic_cert_mode, apic_username, apic_hostname))
    resp = None
    try:
        if apic_cert_mode:
            session = Session(apic_hostname, apic_app_user, appcenter_user=True,
                    cert_name=apic_app_user, key=private_cert,
                    subscription_enabled=subscription_enabled)
        else:
            session = Session(apic_hostname, apic_username, apic_password,
                    subscription_enabled=subscription_enabled)
        resp = session.login(timeout=SESSION_LOGIN_TIMEOUT)
        if resp is not None and resp.ok:
            logger.debug("successfully connected on %s" % apic_hostname)
            return session
        else:
            logger.warn("failed to connect on %s" % apic_hostname)
            session.close()
    except Exception as e:
        logger.error("an error occurred creating session: %s" % (
            traceback.format_exc()))

def subscribe(interests, heartbeat=60.0):
    """ blocking subscription call to one or more objects. calling function must
        provide dict 'interest' which contains the following: 
        {
            "classname": {          # classname in which to subscribe
                "callback": <func>  # callback function for object event
                                    # must accept single argument which is event
            },
        }  

        each event is dict with following attributes:
            "_ts": float timestamp event was received on server
            "imdata": list of objects within the event

        additional kwargs:
            heartbeat (int)         # dead interval to check health of session

        This function returns only when subscriptions exits
    """

    # verify caller arguments
    if type(interests) is not dict or len(interests)==0:
        logger.error("invalid interests for subscription: %s" % interest)
        return
    for cname in interests:
        if type(interests[cname]) is not dict or \
            "callback" not in interests[cname]:
            logger.error("invalid interest %s: %s" % (cname, interest[cname]))
            return
        if not callable(interests[cname]["callback"]):
            logger.error("callback '%s' for %s is not callable" % (
                interests[cname]["callback"], cname))
            return
    try: heartbeat = float(heartbeat)
    except ValueError as e:
        logger.warn("invalid heartbeat '%s', setting to 60.0" % heartbeat)
        heartbeat = 60.0

    # setup subscriptions
    session = get_apic_session(subscription_enabled=True)
    if session is None: 
        logger.warn("failed to get APIC session")
        return
    for cname in interests:
        url = "/api/class/%s.json?subscription=yes&page-size=100" % cname
        interests[cname]["url"] = url
        resp = session.subscribe(url, True)
        if resp is None or not resp.ok:
            logger.warn("failed to subscribe to %s" % cname)
            return
        logger.debug("successfully subscribed to %s" % cname)
    
    # listen for events and send to callback    
    last_heartbeat = time.time()
    while True:
        interest_found = False
        ts = time.time()
        for cname in interests:
            url = interests[cname]["url"]
            count = session.get_event_count(url)
            if count > 0:
                logger.debug("1/%s events found for %s" % (count, cname))
                interests[cname]["callback"](session.get_event(url))
                interest_found = True

        # update last_heartbeat or if exceed heartbeat, check session health
        if interest_found: 
            last_heartbeat = ts
        elif (ts-last_heartbeat) > heartbeat:
            logger.debug("checking session status, last_heartbeat: %s" % (
                last_heartbeat))
            if not check_session_subscription_health(session):
                logger.warn("session no longer alive")
                return
            last_heartbeat = ts
        else: time.sleep(0.1)

def check_session_subscription_health(session):
    """ check health of session subscription thread and that corresponding
        websocket is still connected.  Additionally, perform query on uni to 
        ensure connectivity to apic is still present
        return True if all checks pass else return False
    """
    alive = False
    try:
        alive = (
            hasattr(session.subscription_thread, "is_alive") and \
            session.subscription_thread.is_alive() and \
            hasattr(session.subscription_thread, "_ws") and \
            session.subscription_thread._ws.connected and \
            get_dn(session, "uni") is not None
        )
    except Exception as e: pass
    logger.debug("manual check to ensure session is still alive: %r" % alive)
    return alive

###############################################################################
#
# simplified mongo db functions
#
###############################################################################

def db_is_alive():
    """ perform connection attempt to database and return bool if alive """
    logger.debug("checking if db is alive")
    app = get_app()
    try:
        with app.app_context():
            db = app.mongo.db
            db.collection_names()
            logger.debug("database is alive")
            return True
    except Exception as e: pass
    logger.error("failed to connect to database")
    return False

def init_db():
    """ initalize database by dropping current db and setting up new collection
        indexes
    """
    collections = {
        "dnsDomain": {"key": "dn"},
        "dnsProv": {"key": "dn"},   
        "dnsCache": {"key": "addr"},
    }
    logger.debug("initializing database")
    app = get_app()
    with app.app_context():
        db = app.mongo.db
        for cname in collections:
            logger.debug("initializing collection: %s" % cname)
            db[cname].drop()
            if "key" in collections[cname]:
                indexes = [(collections[cname]["key"], DESCENDING)]
                db[cname].create_index(indexes, unique=True)
    logger.debug("database initialization complete")
