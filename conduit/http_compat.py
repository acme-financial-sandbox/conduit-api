# -*- coding: utf-8 -*-
"""Keep the Flask 1.1 / Werkzeug 1.0 response bytes on Flask 3.

API clients depend on the exact bodies, so JSON responses are serialised the way Flask 1.1
``jsonify`` did and HTML error pages use the Werkzeug 1.0 template.
"""
from flask.json.provider import DefaultJSONProvider
from markupsafe import escape
from werkzeug.exceptions import HTTPException


class LegacyJSONProvider(DefaultJSONProvider):
    """Flask 1.1 ``jsonify``: indent 2 with ``", "`` separators in debug, compact otherwise."""

    def response(self, *args, **kwargs):
        obj = self._prepare_response_obj(args, kwargs)
        if self._app.debug:
            dump_args = {'indent': 2, 'separators': (', ', ': ')}
        else:
            dump_args = {'separators': (',', ':')}
        return self._app.response_class(self.dumps(obj, **dump_args) + '\n',
                                        mimetype='application/json')


def _werkzeug1_get_body(self, environ=None, scope=None):
    return (
        '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">\n'
        '<title>{code} {name}</title>\n'
        '<h1>{name}</h1>\n'
        '{description}\n'
    ).format(code=self.code, name=escape(self.name), description=self.get_description(environ))


HTTPException.get_body = _werkzeug1_get_body
