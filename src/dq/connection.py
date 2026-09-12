"""TLS verification and optional HTTP Basic authentication."""

import base64
import os
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPSHandler, HTTPRedirectHandler
from dq.config import ConfigError
from dq.files import absolute_path


class SameSchemeRedirect(HTTPRedirectHandler):
    """Follow redirects only when the URL scheme stays unchanged."""

    def redirect_request(self, request, response, code, message, headers, new_url):
        original = urlsplit(request.full_url).scheme.lower()
        redirected = urlsplit(new_url).scheme.lower()
        if original != redirected:
            raise URLError('redirect refused: DQ will not switch from {0} to {1}'.format(
                original, redirected))
        return HTTPRedirectHandler.redirect_request(
            self, request, response, code, message, headers, new_url)


class NoRedirect(HTTPRedirectHandler):
    """Authenticated requests must not send credentials to a redirect target."""

    def redirect_request(self, request, response, code, message, headers, new_url):
        raise HTTPError(request.full_url, code,
                        'redirect refused for an authenticated request', headers, response)


class Connection:
    def __init__(self, username=None, password=None, trust_certificate=None):
        if (username is None) != (password is None):
            raise ConfigError('username and password must be supplied together')
        if username is not None and (':' in username or '\n' in username or '\r' in username):
            raise ConfigError('username must not contain a colon or line break')
        self.authenticated = username is not None
        self.authorization = None
        if self.authenticated:
            value = '{0}:{1}'.format(username, password).encode('utf-8')
            self.authorization = 'Basic ' + base64.b64encode(value).decode('ascii')
        try:
            context = ssl.create_default_context()
            if trust_certificate:
                context.load_verify_locations(cafile=trust_certificate)
        except (OSError, ValueError) as error:
            raise ConfigError('could not load trusted certificate: {0}'.format(error))
        handlers = [HTTPSHandler(context=context)]
        handlers.append(NoRedirect() if self.authenticated else SameSchemeRedirect())
        self.opener = build_opener(*handlers)

    def open(self, request):
        if self.authorization:
            request.add_unredirected_header('Authorization', self.authorization)
        return self.opener.open(request, timeout=30)


def connection_values(options, config):
    """Resolve CLI overrides; INI certificate paths are relative to the INI file."""
    values = {}
    for name in ('username', 'password', 'trust_certificate'):
        value = getattr(options, name)
        values[name] = value if value is not None else getattr(config, name)
    certificate = values['trust_certificate']
    if certificate:
        certificate = os.path.expanduser(certificate)
        if options.trust_certificate is None and config.source and not os.path.isabs(certificate):
            certificate = os.path.join(os.path.dirname(config.source), certificate)
        values['trust_certificate'] = absolute_path(certificate)
    return values


def make_connection(options, config):
    values = connection_values(options, config)
    return Connection(**values)
