# -*- coding: utf-8 -*-
"""The app module, containing the app factory function."""
from flask import Flask, current_app
from conduit.extensions import bcrypt, db, migrate, jwt, cors

from conduit import commands, user, profile, articles
from conduit.settings import ProdConfig
from conduit.exceptions import InvalidUsage
from conduit.http_compat import LegacyJSONProvider

CORS_BLUEPRINTS = (user.views.blueprint, profile.views.blueprint, articles.views.blueprint)


class _CorsHookCollector(object):
    """Stands in for a blueprint so Flask-Cors hands over its after_request hook."""

    def after_request(self, hook):
        self.hook = hook
        return hook


def _apply_app_cors(response):
    return current_app.extensions['conduit_cors'](response)


# Flask >= 2.2 refuses after_request() on a blueprint that is already registered, so the CORS
# hook is attached once and each app's own CORS options are looked up per request.
for _blueprint in CORS_BLUEPRINTS:
    _blueprint.after_request(_apply_app_cors)


def create_app(config_object=ProdConfig):
    """An application factory, as explained here:
    http://flask.pocoo.org/docs/patterns/appfactories/.

    :param config_object: The configuration object to use.
    """
    app = Flask(__name__.split('.')[0])
    app.json = LegacyJSONProvider(app)
    app.url_map.strict_slashes = False
    app.config.from_object(config_object)
    register_extensions(app)
    register_blueprints(app)
    register_errorhandlers(app)
    register_shellcontext(app)
    register_commands(app)
    return app


def register_extensions(app):
    """Register Flask extensions."""
    bcrypt.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)


def register_blueprints(app):
    """Register Flask blueprints."""
    origins = app.config.get('CORS_ORIGIN_WHITELIST', '*')
    collector = _CorsHookCollector()
    cors.init_app(collector, origins=origins)
    app.extensions['conduit_cors'] = collector.hook

    for blueprint in CORS_BLUEPRINTS:
        app.register_blueprint(blueprint)


def register_errorhandlers(app):

    def errorhandler(error):
        response = error.to_json()
        response.status_code = error.status_code
        return response

    app.errorhandler(InvalidUsage)(errorhandler)


def register_shellcontext(app):
    """Register shell context objects."""
    def shell_context():
        """Shell context objects."""
        return {
            'db': db,
            'User': user.models.User,
            'UserProfile': profile.models.UserProfile,
            'Article': articles.models.Article,
            'Tag': articles.models.Tags,
            'Comment': articles.models.Comment,
        }

    app.shell_context_processor(shell_context)


def register_commands(app):
    """Register Click commands."""
    app.cli.add_command(commands.test)
    app.cli.add_command(commands.lint)
    app.cli.add_command(commands.clean)
    app.cli.add_command(commands.urls)
