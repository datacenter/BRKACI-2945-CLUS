from flask import Flask, make_response, jsonify
from flask_pymongo import PyMongo

def get_app_config(config_filename="config.py"):
    # returns only the app.config without creating full app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object("config")
    # pass if unable to load instance file
    try: app.config.from_pyfile(config_filename)
    except IOError: pass
    # import private config when running in APP_MODE
    try: app.config.from_pyfile("/home/app/config.py", silent=True)
    except IOError: pass
    return app.config

def create_app(config_filename="config.py"):

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object("config")
    # pass if unable to load instance file
    try: app.config.from_pyfile(config_filename)
    except IOError: pass
    # import private config when running in APP_MODE
    try: app.config.from_pyfile("/home/app/config.py", silent=True)
    except IOError: pass

    # register dependent applications
    app.mongo = PyMongo(app)

    # register blueprints
    from .api import api
    app.register_blueprint(api)

    # register error handlers
    register_error_handler(app)

    # return app instance
    return app


def register_error_handler(app):
    """ register error handler's for common error codes to app """
    def error_handler(error):
        code = getattr(error, "code", 500)
        # default text for error code
        text = {
            400: "Invalid Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "URL not found",
            405: "Method not allowed",
            500: "Internal server error",
        }.get(code, "An unknown error occurred")

        # override text description with provided error description
        if error is not None and hasattr(error, "description") and \
            len(error.description)>0:
            text = error.description

        # return json for all errors for now...
        return make_response(jsonify({"error":text}), code)

    for code in (400,401,403,404,405,500):
        app.errorhandler(code)(error_handler)

    return None

