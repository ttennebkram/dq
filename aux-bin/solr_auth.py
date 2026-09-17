#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# License text: https://www.apache.org/licenses/LICENSE-2.0
"""Switch authentication on the local development SolrCloud instance."""

import argparse
import configparser
import getpass
import json
import os
import shutil
import subprocess
import sys
import tempfile


def run(command, directory):
    subprocess.check_call(command, cwd=directory)


def read_security(solr, directory, zk_host, destination):
    run([solr, 'zk', 'cp', 'zk:/security.json', destination, '-z', zk_host], directory)
    with open(destination, encoding='utf-8') as stream:
        return json.load(stream)


def saved_credentials(directory, replace=False):
    """Keep the local test login independently of Solr's enabled/disabled state."""
    path = os.path.join(directory, 'local-auth.ini')
    config = configparser.ConfigParser(interpolation=None)
    if os.path.isfile(path) and not replace:
        with open(path, encoding='utf-8') as stream:
            config.read_file(stream)
        username = config.get('authentication', 'username')
        password = config.get('authentication', 'password')
    else:
        username = input('Solr username: ').strip()
        password = getpass.getpass('Solr password (saved locally for reuse): ')
        if not username or ':' in username or '\n' in username or '\r' in username:
            raise ValueError('username must be nonempty and contain no colon or line break')
        if not password or '\n' in password or '\r' in password:
            raise ValueError('password must be nonempty and fit on one line')
        if password != password.strip():
            raise ValueError('saved password must not begin or end with whitespace')
        config.add_section('authentication')
        config.set('authentication', 'username', username)
        config.set('authentication', 'password', password)
        descriptor, temporary = tempfile.mkstemp(prefix='.local-auth-', dir=directory)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                config.write(stream)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
        print('Saved local login: {0}'.format(path), flush=True)
    if not username or ':' in username or not password:
        raise ValueError('saved login is invalid; use --set_credentials to replace it')
    return username + ':' + password


def main(argv=None):
    script_directory = os.path.dirname(os.path.realpath(__file__))
    installation = script_directory
    if not os.path.isfile(os.path.join(installation, 'bin', 'solr')):
        installation = os.path.dirname(script_directory)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('on', 'off', 'status'))
    parser.add_argument('--solr_dir', default=installation, metavar='DIR')
    parser.add_argument('--set_credentials', action='store_true',
                        help='with on, prompt for and replace the saved local login')
    parser.add_argument('--restart', action='store_true',
                        help='also restart this local SolrCloud node after changing auth')
    parser.add_argument('--port', type=int, default=8983)
    options = parser.parse_args(argv)
    if not 1 <= options.port <= 55535:
        parser.error('port must be between 1 and 55535 (embedded ZooKeeper uses port + 1000)')
    if options.set_credentials and options.mode != 'on':
        parser.error('--set_credentials is only valid with on')
    directory = os.path.realpath(os.path.expanduser(options.solr_dir))
    solr = os.path.join(directory, 'bin', 'solr')
    if not os.path.isfile(solr):
        parser.error('Solr installation not found; use --solr_dir DIR')
    zk_host = '127.0.0.1:{0}'.format(options.port + 1000)
    include = os.path.join(directory, 'bin', 'solr.in.sh')
    # Backup directories and CLI-generated credential files are owner-only.
    previous_umask = os.umask(0o077)
    try:
        with tempfile.TemporaryDirectory(prefix='solr_auth-') as temporary:
            security_file = os.path.join(temporary, 'security.json')
            security = read_security(solr, directory, zk_host, security_file)
            authentication = security.get('authentication') or {}
            plugin = authentication.get('class')
            enabled = bool(plugin)
            if options.mode == 'status':
                print('Authentication: {0}'.format(plugin if enabled else 'off'))
                if enabled:
                    print('Anonymous requests blocked: {0}'.format(
                        authentication.get('blockUnknown', True)))
                return 0
            if options.mode == 'on' and enabled:
                raise ValueError('authentication is already configured; use status to inspect it')
            if options.mode == 'off' and not enabled:
                print('Authentication is already off.')
            else:
                if plugin and plugin not in ('solr.BasicAuthPlugin', 'org.apache.solr.security.BasicAuthPlugin'):
                    raise ValueError('refusing to replace a non-Basic authentication plugin')
                backup_root = os.path.join(directory, 'local-auth-backups')
                if not os.path.isdir(backup_root):
                    os.mkdir(backup_root, 0o700)
                backup = tempfile.mkdtemp(prefix='before-' + options.mode + '-', dir=backup_root)
                shutil.copyfile(security_file, os.path.join(backup, 'security.json'))
                for name, source in [('solr.in.sh', include),
                                     ('basicAuth.conf', os.path.join(directory, 'server', 'solr', 'basicAuth.conf'))]:
                    if os.path.isfile(source):
                        shutil.copyfile(source, os.path.join(backup, name))
                print('Saved previous configuration: {0}'.format(backup), flush=True)
                command = [solr, 'auth', 'enable' if options.mode == 'on' else 'disable',
                           '-z', zk_host, '--solr-include-file', include,
                           '--auth-conf-dir', os.path.join(directory, 'server', 'solr')]
                if options.mode == 'on':
                    credentials = saved_credentials(directory, replace=options.set_credentials)
                    command.extend(['--type', 'basicAuth', '--credentials', credentials,
                                    '--block-unknown', 'true'])
                run(command, directory)
                updated = read_security(solr, directory, zk_host, security_file)
                if bool((updated.get('authentication') or {}).get('class')) != (options.mode == 'on'):
                    raise ValueError('Solr did not save the requested authentication state')
                print('Authentication is now {0}.'.format(options.mode))
            if options.restart:
                run([solr, 'restart', '--cloud', '-p', str(options.port), '--host', 'localhost'], directory)
            else:
                print('SolrCloud applies the security change live; no restart requested.')
        return 0
    except subprocess.CalledProcessError:
        print('solr_auth: Solr command failed; saved configuration backups are retained.', file=sys.stderr)
        return 1
    except (OSError, ValueError, configparser.Error) as error:
        print('solr_auth: {0}'.format(error), file=sys.stderr)
        print('Solr and its embedded ZooKeeper must be running. Any saved backup is retained.', file=sys.stderr)
        return 1
    finally:
        os.umask(previous_umask)


if __name__ == '__main__':
    sys.exit(main())
