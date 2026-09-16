"""Quick field-presence report without a stored-value scan."""
from dq.reports.checkup import write_report as _write_report


def write_report(target, output_path, **options):
    return _write_report(target, output_path, mode='lite', report_name='quick_checkup', **options)
