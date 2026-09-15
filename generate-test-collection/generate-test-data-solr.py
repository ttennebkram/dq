#!/usr/bin/env python3
"""Generate test records for Solr."""
import sys
from test_data import main

if __name__ == '__main__':
    sys.exit(main(backend='solr'))
