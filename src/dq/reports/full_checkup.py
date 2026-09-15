"""complete stored-value scan with text and regex checks."""
from dq.reports.checkup import write_report as _write_report


def write_report(target, output_path, **options):
    return _write_report(target, output_path, mode='full', report_name='full_checkup', **options)
