#!/usr/bin/env python3
"""Generate repeatable synthetic fixtures with independently selected errors per field."""
import argparse
import json
import os
import random
import sys

FIELDS = ['first_name_t', 'last_name_t', 'street_address_t', 'city_t', 'state_t',
          'postal_code_t', 'country_t', 'email_t', 'phone_t', 'ssn_t', 'event_date_dt', 'notes_t']


def valid_values(index):
    return dict(zip(FIELDS, ['DemoName{0}'.format(index), 'ExampleFamily',
        '{0} Example Street'.format(index), 'Example City', 'CA', '90001', 'US',
        'demo{0}@example.com'.format(index), '212-555-{0:04d}'.format(100 + index % 100),
        '123-45-{0:04d}'.format(1000 + index % 9000), '2024-01-15T00:00:00Z', 'Synthetic example text']))


def generate(count, incorrect_percent=20.0, seed=None):
    if count < 1:
        raise ValueError('count must be positive')
    percentages = dict((field, incorrect_percent) for field in FIELDS)
    if any(not 0 <= percent <= 100 for percent in percentages.values()):
        raise ValueError('percentages must be between 0 and 100')
    if seed is None:
        seed = random.SystemRandom().getrandbits(128)
    rng = random.Random(seed)
    documents = [dict(valid_values(i), id='demo-{0:06d}'.format(i)) for i in range(1, count + 1)]
    findings = []
    summary = {}
    kinds = ['missing', 'null', 'empty string', 'whitespace only', 'malformed']
    malformed = {'email_t':'not-an-email', 'phone_t':'123', 'ssn_t':'000-12-3456',
                 'event_date_dt':'2999-01-01T00:00:00Z', 'notes_t':'Replacement character: \ufffd'}
    for field in FIELDS:
        number = int(count * percentages[field] / 100.0 + 0.5)
        chosen = rng.sample(range(count), number)
        summary[field] = {'requested_percent': percentages[field], 'incorrect_documents': number,
                          'actual_percent': 100.0 * number / count}
        for sequence, index in enumerate(chosen):
            categories = ['missing', 'null', 'future date'] if field == 'event_date_dt' else kinds
            kind = categories[sequence % len(categories)]
            doc = documents[index]
            if kind == 'missing':
                del doc[field]
            else:
                doc[field] = {'null':None, 'empty string':'', 'whitespace only':' \t\n',
                              'future date':'2999-01-01T00:00:00Z',
                              'malformed':malformed.get(field, '???\ufffd')}[kind]
            findings.append({'id':doc['id'], 'field':field, 'kind':kind})
    return documents, {'synthetic':True, 'seed':seed, 'documents':count,
                       'fields':summary, 'injected_errors':findings}


def main(argv=None, backend='solr'):
    parser = argparse.ArgumentParser(
        prog='generate-test-data-' + backend + '.py', description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""From the project root, first run: cd generate-test-collection

Examples:
  # Run from inside generate-test-collection/
  ./generate-test-data.py --count 1000 --incorrect_percent 20
  ./generate-test-data.py --count 1000 --incorrect_percent 25 --seed 42

RANDOM BY DEFAULT: omit --seed for a fresh run.
REPEATABLE: supply --seed N with the same options and generator/Python version.
The chosen seed is printed and saved in expected-results.json, including for random runs.
Seeds 0 and -1 are ordinary repeatable seeds, not special random modes.

Writes documents-solr.json and expected-results.json in the current working directory.
--data_files_dir is relative to the current directory unless an absolute path is given.
Reusable schema/config files, the loader, and demo notes live in generate-test-collection/.
Does not submit data to Solr.
Load generated data from this directory with:
  ./submit-to-solr.py --submit
The loader searches upward for ../dq.ini.
Add --recreate_collection to the loader to rebuild the demo collection.

Fields: """ + ', '.join(FIELDS))
    parser.epilog = parser.epilog.replace('generate-test-data.py', parser.prog)
    if backend == 'es':
        parser.epilog = parser.epilog.replace('documents-solr.json', 'documents-es.ndjson').replace(
            'Does not submit data to Solr.', 'Elasticsearch and OpenSearch share this bulk format. No data is submitted.').replace(
            './submit-to-solr.py --submit', './submit-to-es.py --submit (supports Elasticsearch and OpenSearch; use --main_url for the target)').replace(
            '--recreate_collection', '--recreate_index')
    parser.add_argument('--count', type=int, required=True, help='required number of documents; suggested starting count: 1000 (no default)')
    parser.add_argument('--incorrect_percent', '--incorrect-percent', type=float, default=20, help='incorrect records per field, 0-100 percent (default: 20)')
    parser.add_argument('--seed', type=int, default=None, help='repeatable integer seed; omit for fresh randomness (0 and -1 are repeatable too)')
    default_directory = '.'
    parser.add_argument('--data_files_dir', '--data-files-dir', default=default_directory, help='directory for generated documents and expected-results.json (default: current directory; relative or absolute path)')
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    try:
        documents, expected = generate(args.count, args.incorrect_percent, args.seed)
    except ValueError as error:
        parser.error(str(error))
    if not os.path.isdir(args.data_files_dir):
        os.makedirs(args.data_files_dir)
    payload_name = 'documents-solr.json' if backend == 'solr' else 'documents-es.ndjson'
    with open(os.path.join(args.data_files_dir, payload_name), 'w', encoding='utf-8') as stream:
        if backend == 'solr':
            json.dump(documents, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write('\n')
        else:
            for doc in documents:
                stream.write(json.dumps({'index': {'_id': doc['id']}}, ensure_ascii=False) + '\n')
                stream.write(json.dumps(doc, ensure_ascii=False, sort_keys=True) + '\n')
    with open(os.path.join(args.data_files_dir, 'expected-results.json'), 'w', encoding='utf-8') as stream:
        json.dump(expected, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write('\n')
    print('Data file: ' + os.path.join(args.data_files_dir, payload_name))
    print('Generated {0} synthetic documents; seed: {1}.'.format(args.count, expected['seed']))
    print('Repeat with --seed {0} and the same options. Answer key: {1}'.format(
        expected['seed'], os.path.join(args.data_files_dir, 'expected-results.json')))
