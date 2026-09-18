#!/usr/bin/env python3
"""Generate repeatable synthetic fixtures with independently selected errors per field."""
import argparse
import json
import os
import random
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_ROOT = os.path.join(PROJECT_ROOT, 'src')
if SOURCE_ROOT not in sys.path:
    sys.path.insert(0, SOURCE_ROOT)

from dq.rules.synthetic_values import (MISSING, common_invalid_value,
                                       defect_plan, standard_text_defect_plan)
from dq.rules.code_points_base.synthetic_values import invalid_values as invalid_text
from dq.rules.email_base.synthetic_values import invalid_values as invalid_email
from dq.rules.us_phone_base.synthetic_values import invalid_values as invalid_phone
from dq.rules.ssn_base.synthetic_values import invalid_values as invalid_ssn
from dq.rules.part_number_example_base.synthetic_values import invalid_values as invalid_part_number

FIELDS = ['first_name_t', 'last_name_t', 'street_address_t', 'city_t', 'state_t',
          'postal_code_t', 'country_t', 'email_t', 'phone_t', 'ssn_t',
          'part_number_s', 'event_date_dt', 'notes_t']
FORMAT_FIELDS = set(('email_t', 'phone_t', 'ssn_t', 'part_number_s'))


def valid_values(index):
    return dict(zip(FIELDS, ['DemoName{0}'.format(index), 'ExampleFamily',
        '{0} Example Street'.format(index), 'Example City', 'CA', '90001', 'US',
        'demo{0}@example.com'.format(index), '212-555-{0:04d}'.format(100 + index % 100),
        '123-45-{0:04d}'.format(1000 + index % 9000),
        'PRT-{0:06d}'.format(index % 1000000),
        '2024-01-15T00:00:00Z', 'Synthetic example text']))


def malformed_value(field, index, sequence):
    valid = valid_values(index + 1)[field]
    generator = {
        'email_t': invalid_email,
        'phone_t': invalid_phone,
        'ssn_t': invalid_ssn,
        'part_number_s': invalid_part_number,
    }.get(field, invalid_text)
    values = generator(valid, index + 1)
    return values[(index + sequence) % len(values)]


def invalid_date(index, sequence):
    values = ('2099-12-31T23:59:59Z', '2199-06-15T12:00:00Z',
              '2999-01-01T00:00:00Z', '9999-12-31T23:59:59Z')
    return values[(index + sequence) % len(values)]


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
    for field in FIELDS:
        number = int(count * percentages[field] / 100.0 + 0.5)
        chosen = rng.sample(range(count), number)
        if field == 'event_date_dt':
            planned_defects = [None] * number
        elif field in FORMAT_FIELDS:
            planned_defects = defect_plan(number)
        else:
            planned_defects = standard_text_defect_plan(number)
        rng.shuffle(planned_defects)
        for sequence, (index, planned_defect) in enumerate(zip(chosen, planned_defects)):
            doc = documents[index]
            if field == 'event_date_dt':
                kind = ('missing', 'null', 'future_date')[sequence % 3]
                if kind == 'missing':
                    del doc[field]
                elif kind == 'null':
                    doc[field] = None
                else:
                    doc[field] = invalid_date(index, sequence)
            else:
                kind = planned_defect
                if kind == 'rule':
                    doc[field] = malformed_value(field, index, sequence)
                else:
                    value = common_invalid_value(kind, doc[field])
                    if value is MISSING:
                        del doc[field]
                    else:
                        doc[field] = value
    return documents, seed


def document_count(value):
    """Parse a document count, including Python-style underscore separators."""
    try:
        return int(value.replace('_', ''))
    except (AttributeError, ValueError):
        raise argparse.ArgumentTypeError('must be an integer such as 1000 or 1_000')


def main(argv=None, backend='solr'):
    parser = argparse.ArgumentParser(
        prog='generate_test_data_' + backend + '.py', description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Assumes you're in the generate_test_collection directory under the main dq project directory.

Examples:
  # Run from inside generate_test_collection/
  ./generate_test_data.py --rows 1000
  ./generate_test_data.py --rows 1000 --incorrect_percent 25 --seed 42

Writes demo data to documents_solr.json in the current working directory if --data_files_dir is not used.
To actually submit the generated documents to Solr, use submit_to_solr.py.

Generated Fields: """ + ', '.join(FIELDS))
    parser.epilog = parser.epilog.replace('generate_test_data.py', parser.prog)
    if backend == 'es':
        parser.epilog = parser.epilog.replace('documents_solr.json', 'documents_es.ndjson').replace(
            'To actually submit the generated documents to Solr, use submit_to_solr.py.',
            'To actually submit the generated documents to Elasticsearch or OpenSearch, use submit_to_es.py.')
    parser.add_argument('--rows', '--size', dest='rows', metavar='N', type=document_count,
                        help='required number of documents; --size is equivalent; suggested starting value: 1000')
    parser.add_argument('--incorrect_percent', type=float, default=20, help='incorrect records per field, 0-100 percent (default: 20)')
    parser.add_argument('--incorrect-percent', dest='incorrect_percent', type=float,
                        help=argparse.SUPPRESS)
    parser.add_argument('--seed', type=int, default=None, help='repeatable integer random seed; omit for fresh randomness (0 and -1 are repeatable too)')
    default_directory = '.'
    parser.add_argument('--data_files_dir', default=default_directory, help='directory for generated documents (default: current directory; relative or absolute path)')
    parser.add_argument('--data-files-dir', dest='data_files_dir', help=argparse.SUPPRESS)
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    if args.rows is None:
        parser.error('--rows is required (--size is equivalent)')
    try:
        documents, seed = generate(args.rows, args.incorrect_percent, args.seed)
    except ValueError as error:
        parser.error(str(error))
    if not os.path.isdir(args.data_files_dir):
        os.makedirs(args.data_files_dir)
    payload_name = 'documents_solr.json' if backend == 'solr' else 'documents_es.ndjson'
    with open(os.path.join(args.data_files_dir, payload_name), 'w', encoding='utf-8') as stream:
        if backend == 'solr':
            json.dump(documents, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write('\n')
        else:
            for doc in documents:
                stream.write(json.dumps({'index': {'_id': doc['id']}}, ensure_ascii=False) + '\n')
                stream.write(json.dumps(doc, ensure_ascii=False, sort_keys=True) + '\n')
    print('Data file: ' + os.path.join(args.data_files_dir, payload_name))
    print('Generated {0} synthetic documents; seed: {1}.'.format(args.rows, seed))
    print('')
    if backend == 'es':
        print('REMINDER: Submit {0} to Elasticsearch/OpenSearch with submit_to_es.py --submit'.format(payload_name))
    else:
        print('REMINDER: Submit {0} to Solr with submit_to_solr.py --submit'.format(payload_name))
