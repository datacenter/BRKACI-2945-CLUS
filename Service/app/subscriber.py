
import logging, sys
from .utils import (setup_logger, get_app, pretty_print, db_is_alive, init_db,
    get_apic_session, get_class, subscribe,
)

# module level logging
logger = logging.getLogger(__name__)

def dns_subscriptions(db):
    """ build subscription to APIC dns objects and keep consistent values in 
        database.  On startup, simply wipe the db since we'll be pulling new 
        objects (and any cached entries can be considered invalid on startup)
        
        dnsDomain   
            - multiple domains supported, only one is 'default'
            - track 'name' and 'isDefault' (yes/no)
            - only support dnsp-default
        dnsProv
            - multiple providers supported, only one is preferred
            - track 'addr' which should be unique and 'preferred' (yes/no)
            - only support dnsp-default
    """

    # initialize db to clear out all existing objects
    init_db()
  
    # read initial state and insert into database 
    (domains, providers) = ([], [])
    session = get_apic_session()
    if session is None: 
        logger.error("unable to connect to APIC")
        return
    dnsDomain = get_class(session, "dnsDomain")
    dnsProv = get_class(session, "dnsProv")
    if dnsDomain is None or dnsProv is None:
        logger.error("failed to perform dns init")
        return
    for obj in dnsDomain:
        attr = obj[obj.keys()[0]]["attributes"]
        if "name" in attr and "dn" in attr and "isDefault" in attr:
            if "/dnsp-default/" in attr["dn"]:
                domains.append({
                    "dn": attr["dn"],
                    "name":attr["name"], 
                    "isDefault": True if attr["isDefault"]=="yes" else False
                })
    for obj in dnsProv:
        attr = obj[obj.keys()[0]]["attributes"]
        if "addr" in attr and "dn" in attr and "preferred" in attr:
            if "/dnsp-default/" in attr["dn"]:
                providers.append({
                    "dn": attr["dn"],
                    "addr":attr["addr"],
                    "preferred": True if attr["preferred"]=="yes" else False
                })
    # insert domains and providers into database
    logger.debug("inserting domains: %s, and providers: %s"%(domains,providers))
    db.dnsDomain.insert_many(domains)
    db.dnsProv.insert_many(providers)
        
    # setup subscriptions to interesting objects
    interests = {
        "dnsDomain": {"callback": handle_dns_event},
        "dnsProv": {"callback": handle_dns_event},
    }
    subscribe(interests)
    logger.error("subscription unexpectedly ended")
    

def handle_dns_event(event):
    """ handle created, deleted, modified events for dnsProv and dnsDomain by
        updating corresponding object in db.
        On successful create/delete clear dnsCache
    """
    if "imdata" in event and type(event["imdata"]) is list:
        for obj in event["imdata"]:
            cname = obj.keys()[0]
            attr = obj[cname]["attributes"]
            if "status" not in attr or "dn" not in attr or \
                attr["status"] not in ["created","modified", "deleted"]:
                logger.warn("skipping invalid event for %s: %s" % (attr,cname))
                continue
            if cname not in ["dnsProv", "dnsDomain"]:
                logger.debug("skipping event for classname %s" % cname)
                continue

            db_attr = ["dn"]
            if cname == "dnsDomain": db_attr+=["name", "isDefault"]
            else: db_attr+=["addr", "preferred"]

            # create object that will be added/deleted/updated in db
            obj = {}
            for a in db_attr: 
                if a in attr: obj[a] = attr[a]
            if "isDefault" in obj: 
                obj["isDefault"] = True if obj["isDefault"]=="yes" else False
            if "preferred" in obj:
                obj["preferred"] = True if obj["preferred"]=="yes" else False

            logger.debug("%s %s obj:%s" % (cname, attr["status"], obj))
            if attr["status"] == "created" or attr["status"] == "modified":
                ret = db[cname].update_one(
                    {"dn":attr["dn"]}, {"$set":obj}, upsert=True
                )
                logger.debug("update_one match/modify/upsert: [%s,%s,%s]" % (
                    ret.matched_count, ret.modified_count, ret.upserted_id))
        
            if attr["status"] == "deleted":
                ret = db[cname].delete_one({"dn":attr["dn"]})
                logger.debug("delete_one deleted: %s" % ret.deleted_count)

            if attr["status"] == "created" or attr["status"] == "deleted":
                logger.debug("clearing dnsCache")
                db["dnsCache"].drop()



if __name__ == "__main__":

    # main can be used to run subscription or just to test db access
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--check_db", action="store_true", dest="check_db",
        help="check for successful db connection")
    args = parser.parse_args()

    try:
        # setup local logger along with 'app' logger
        logger = setup_logger(logger, "subscriber.log", quiet=True)
        setup_logger(logging.getLogger("app"), "subscriber.log", quiet=True)

        # check db is alive before executing background subscriber
        if not db_is_alive():   
            logger.error("unable to connect to db")
            sys.exit(1)

        if args.check_db:
            # successfully checked db already
            sys.exit(0)

        # run subscriptions which only stop on error    
        app = get_app()
        with app.app_context():
            db = app.mongo.db
            dns_subscriptions(db) 

    except KeyboardInterrupt as e:
        print "\ngoodbye!\n"
        sys.exit(1)
 
