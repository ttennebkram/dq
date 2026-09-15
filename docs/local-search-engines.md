# Native local Elasticsearch and OpenSearch

Both installations live alongside `dq` under `~/Dropbox/dev`, with separate
`data/`, `logs/`, and `run/` directories. They run simultaneously without Docker.

| Engine | Directory | HTTP | Transport |
| --- | --- | --- | --- |
| Elasticsearch 9.5.3 | `elasticsearch-9.5.3` | 9200 | 9300 |
| OpenSearch 3.8.0 | `opensearch-3.8.0` | 9201 | 9301 |

These development instances bind to `127.0.0.1`, use HTTP without authentication,
and have a 1 GiB Java heap each. Elasticsearch uses its bundled macOS ARM JDK.
OpenSearch uses the minimal ARM archive and the installed native Temurin JDK 21.
They are single-node clusters; demo indexes have one shard and zero replicas.
Startup is manual, not registered as a login service.

## Start

Run only when the corresponding server is stopped:

```bash
cd ~/Dropbox/dev/elasticsearch-9.5.3
bin/elasticsearch -d -p "$PWD/run/elasticsearch.pid"

cd ~/Dropbox/dev/opensearch-3.8.0
export OPENSEARCH_JAVA_HOME="$(/usr/libexec/java_home -v 21)"
bin/opensearch -d -p "$PWD/run/opensearch.pid"
```

Allow startup time before loading data. Check identity and health:

```bash
curl http://localhost:9200/
curl http://localhost:9201/
curl 'http://localhost:9200/_cluster/health?pretty'
curl 'http://localhost:9201/_cluster/health?pretty'
```

Application logs live in each installation's `logs/` directory. The initial
installation's captured startup output is `logs/dq-startup.log`.

## Stop

Inspect the recorded PID before signaling it; it must belong to that engine and
installation. If the server is already stopped, an old PID could be reused.

```bash
cd ~/Dropbox/dev/elasticsearch-9.5.3
ps -p "$(cat run/elasticsearch.pid)" -o pid=,command=
# After confirming it is this Elasticsearch process:
kill -TERM "$(cat run/elasticsearch.pid)"

cd ~/Dropbox/dev/opensearch-3.8.0
ps -p "$(cat run/opensearch.pid)" -o pid=,command=
# After confirming it is this OpenSearch process:
kill -TERM "$(cat run/opensearch.pid)"
```

A normal shutdown preserves indexes in `data/`. For backups while running,
use each engine's snapshot API; ordinary copying of a live data directory is
not a consistent backup. Dropbox synchronization is not an index backup.

## Installation configuration

Archives and official SHA-512 checksum files were downloaded to `~/Downloads`
and verified before extraction. Elasticsearch is the macOS ARM distribution;
OpenSearch is `opensearch-min-3.8.0-linux-arm64.tar.gz`, run with native macOS
Java as described in the OpenSearch tar installation instructions.

`config/elasticsearch.yml` and `config/opensearch.yml` set `network.host` to
`127.0.0.1`, `discovery.type` to `single-node`, distinct cluster/node names,
the ports above, and explicit data/log paths. Original distribution configuration
is saved as `config/<engine>.yml.distribution-original`.
`config/jvm.options.d/dq-heap.options` sets `-Xms1g` and `-Xmx1g`.
Elasticsearch security/enrollment, machine learning, and automatic GeoIP downloads
are disabled for this local fixture. OpenSearch minimal has no security plugin.

Official instructions: [Elasticsearch archive installation](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-from-archive-on-linux-macos)
and [OpenSearch tar installation](https://docs.opensearch.org/latest/install-and-configure/install-opensearch/tar/).

## Generate and load

```bash
cd ~/Dropbox/dev/dq/generate-test-collection
./generate-test-data-es.py --count 1000
./submit-to-es.py --submit
./submit-to-es.py --submit --main_url http://localhost:9201
curl 'http://localhost:9200/dq-demo/_search?q=*&size=3&pretty'
curl 'http://localhost:9201/dq-demo/_search?q=*&size=3&pretty'
```

`submit-to-es.py` supports both Elasticsearch and OpenSearch; only the target
URL differs in these examples.

See the [generator guide](../generate-test-collection/README.md) for seeds,
incorrect-value percentages, connection settings, and index recreation.
