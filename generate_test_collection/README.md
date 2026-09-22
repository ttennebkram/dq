# Generate a Test Collection

See the "Generate a Test Collection" section in the main `README.md` file for the
generation and loading instructions.

The four user-facing Python scripts have matching Windows launchers:

| Python script | Windows launcher | Purpose |
| ------------- | ---------------- | ------- |
| `generate_test_data_solr.py` | `generate_test_data_solr.cmd` | Generate synthetic Solr documents. |
| `submit_to_solr.py` | `submit_to_solr.cmd` | Create or update the Solr `dq_demo` collection. |
| `generate_test_data_es.py` | `generate_test_data_es.cmd` | Generate the shared Elasticsearch/OpenSearch documents. |
| `submit_to_es.py` | `submit_to_es.cmd` | Create or update the Elasticsearch/OpenSearch `dq_demo` index. |

On macOS and Linux, run a Python script directly with `./SCRIPT.py`. On Windows,
run its launcher as `.\SCRIPT.cmd`; the `.\` prefix works in PowerShell and
Command Prompt without putting the current directory on `PATH`. Each launcher
uses `py.exe -3`, forwards all arguments, and returns the Python script's exit
status.

Both submission scripts accept `--recreate_collection` and `--recreate_index`
as synonyms for recreating an empty `dq_demo` target without submitting data.
