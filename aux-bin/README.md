# Auxiliary scripts

These optional helpers support local development and testing. The main DQ
command remains in `bin/dq`.

## solr-auth

A standalone Python 3.4.10+ helper for enabling, disabling, and inspecting Basic
authentication on a local SolrCloud installation with embedded ZooKeeper.

Copy `solr-auth` into the target Solr installation's `local-scripts/` directory
(recommended), its existing `bin/` directory, or the installation root. Make the
copied script executable with `chmod +x`. See the
[main README installation instructions](../README.md#install-the-optional-solr-helper)
for full commands.

From the Solr installation root, using the recommended layout:

```sh
./local-scripts/solr-auth status
./local-scripts/solr-auth on
./local-scripts/solr-auth off
```

The first `on` prompts for credentials and saves them in plaintext in the Solr
root's `local-auth.ini`, with owner-only permissions. Subsequent runs reuse them;
`off` keeps the file. To replace them, use `off`, then `on --set_credentials`.
No password file is stored in this DQ directory. Solr and embedded ZooKeeper
must already be running. Changes apply live; `--restart` also restarts Solr.

Use `--solr_dir DIR` when running from outside the Solr installation. The default
Solr port is 8983, with embedded ZooKeeper on 9983; `--port` changes these defaults.
The installed copy has no dependency on the DQ checkout. Recopy after updating
this source; copies are not synchronized automatically.
