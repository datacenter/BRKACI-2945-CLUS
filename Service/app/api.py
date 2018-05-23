
import logging, time
from dns import resolver, reversename, exception
from flask import Blueprint, jsonify, abort, current_app
from .utils import (setup_logger, get_apic_session, get_class, get_user_params)
api = Blueprint("/", __name__)

# module level logging
logger = setup_logger(logging.getLogger(__name__))

@api.route('/is_ready.json')
def is_alive():
    """ api to verify server is alive """
    return jsonify({'status': '200', 'text': "It's alive !"})

@api.route('/tenant.json')
def get_tenant():
    """ test api that returns all tenants - just for fun """
    session = get_apic_session()
    if session is None: abort(500, "unable to connect to APIC")
    
    objects = get_class(session, "fvTenant") 
    if objects is None: abort(500, "unable to query fvTenants")
    
    # let's just return tenant names
    tenants = []
    for obj in objects:
        attr = obj[obj.keys()[0]]["attributes"]
        tenants.append(attr["name"])
    return jsonify({"tenants":tenants})

@api.route("/resolve.json")
def resolve():
    """ resolve dns for provided ipv4 or ipv6 address. This function will check
        local dnsCache in database for entry first. If present and has not yet
        expired, then return cached value. If not present then add result to 
        dnsCache before returning
        
        if entry does not exists return empty n/a.  Abort with 500 on error
    """
    ts = time.time()
    ip = get_user_params().get("ip", None)
    if ip is None or len(ip)==0:
        abort(400, "ip parameter required for resolve")

    # check cache first
    logger.debug("checking dnsCache for %s" % ip)
    db = current_app.mongo.db
    cache = db.dnsCache.find_one({"addr":ip})
    if cache is not None:
        # check that entry did not expire
        delta = cache["expire"] - ts
        if delta <= 0:
            logger.debug("cache entry expired at %s (%ssec)" % (
                cache["expire"], -1*delta))
        else:
            logger.debug("returning result from cache: %s, (timeout:%ssec)"%(
                cache, delta))
            return jsonify({"ip":ip, "ptr":cache["ptr"], "cache":True})

    # no hit on the cache, collect nameserver info and perform lookup
    nameservers = []
    for prov in db.dnsProv.find({}):
        if prov["preferred"]: nameservers.insert(0, prov["addr"])
        else: nameservers.append(prov["addr"])
    
    if len(nameservers) == 0:
        abort(500, "no dnsProv configured on apic")
    logger.debug("dns lookup for %s against %s" % (ip, nameservers))

    r = resolver.Resolver()
    try:
        lookup = r.query(reversename.from_address(ip), "PTR")
        (ptr, expire) = (lookup[0].to_text(), lookup.expiration)
    except resolver.NXDOMAIN as e:
        logger.debug("resolver not found: %s" % e)
        (ptr, expire) = ("n/a", ts+600)     # cache for 10 minutes
    except exception.SyntaxError as e:
        # should only be raised on invalid address
        abort(500, "invalid address %s" % ip)

    # add entry to cache
    cache = {"addr":ip, "ptr":ptr, "expire":expire}
    logger.debug("returning and adding result to cache: %s" % cache)
    db.dnsCache.update_one({"addr":ip}, {"$set":cache}, upsert=True)

    # return result
    return jsonify({"ip":ip,"ptr":cache["ptr"], "cache":False})
