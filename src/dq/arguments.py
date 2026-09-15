"""Command-line syntax and help."""
import argparse
from dq import __version__
from dq.limits import row_limit, progress_interval, boolean_option
from dq.processors.registry import report_names, csv_names, report_help, rule_help


class ExactArgumentParser(argparse.ArgumentParser):
    """Disable abbreviated options without requiring Python 3.5's allow_abbrev."""

    def _get_option_tuples(self, option_string):
        return []


class DqHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Keep accepted hyphen aliases out of the compact syntax display."""

    def _format_action_invocation(self, action):
        if not action.option_strings:
            return super()._format_action_invocation(action)
        visible = [option for option in action.option_strings
                   if '-' not in option.lstrip('-')]
        if not visible:
            visible = action.option_strings[:1]
        if action.nargs == 0:
            return ', '.join(visible)
        default = self._get_default_metavar_for_optional(action)
        arguments = self._format_args(action, default)
        return ', '.join(option + ' ' + arguments for option in visible)


def build_parser():
    def help_formatter(prog):
        return DqHelpFormatter(
            prog, max_help_position=34, width=110)

    parser = ExactArgumentParser(
        prog="dq",
        add_help=False,
        usage="""%(prog)s --list_fields --main_url URL --collection NAME
       %(prog)s --list_fields  (assumes reading other parameters from dq.ini)
       %(prog)s --list_reports
       %(prog)s --list_rules
       %(prog)s --rule NAME [NAME ...] --action csv
       %(prog)s --report NAME [NAME ...]
       %(prog)s --write_config
       %(prog)s --config_wizard
       %(prog)s --help
       %(prog)s --version""",
        formatter_class=help_formatter,
        description="""\
DQ2 is a command-line data-quality toolkit for Apache Solr, Elasticsearch,
and OpenSearch. Only stored fields are included in this version.

Use a special report for summaries, or a rule with the CSV action for detailed
findings. See README.md, especially “Quickstart,” “Automatic Checkup,” and
“Rules, Reports and Actions,” for explanations and examples.""",
        epilog="""\
Rules:
{rule_catalog}

Special Reports:
{report_catalog}

Examples:
  bin/dq --report quick_checkup
  bin/dq --report full_checkup
  bin/dq --rule missing_fields --action csv --include_field email_t
  bin/dq --rule whitespace_only --action csv --include_field notes_t
  bin/dq --rule us_phone --action csv --include_field phone_t

Configuration options: dq.ini in the current directory or a parent directory.
Command-line options override saved settings.

More help: README.md — “Using the DQ Tool” and “Rules, Reports and Actions.”
""".format(report_catalog=report_help(), rule_catalog=rule_help()),
    )
    parser._optionals.title = "Options"
    target_options = parser.add_argument_group("Configuration, Target, and Output")
    actions = parser.add_argument_group("Actions")
    commands = parser.add_argument_group("Utility Commands (choose one)")
    field_options = parser.add_argument_group("Field Selection")
    output_options = parser.add_argument_group("Output and Scanning")

    actions.add_argument(
        "--report",
        "--reports",
        metavar="NAME",
        action="append",
        nargs="+",
        default=[],
        help="run one or more named special reports; synonyms; implies --action report",
    )
    rules = actions
    rules.add_argument('--rule', '--rules', metavar='NAME', action='append', nargs='+', default=[],
                       help='rules to evaluate in order; repeatable; every rule must pass; --rules is a synonym')
    actions.add_argument('--action', choices=('report', 'csv'),
                         help='csv requires --rule/--rules; report requires --report/--reports and is implied by either')
    commands.add_argument(
        "--version",
        action="version",
        version="%(prog)s {0}".format(__version__),
    )
    commands.add_argument('--list_reports', '--list-reports', action='store_true',
                          help='list special reports and implementation status on stdout')
    commands.add_argument('--list_rules', '--list-rules', action='store_true',
                          help='list rules, Base/Composite type, and description on stdout')
    commands.add_argument(
        "--write_config",
        "--write-config",
        action="store_true",
        help="write settings to ./dq.ini or the file named by --config",
    )
    commands.add_argument('--config_wizard', '--config-wizard', '--setup_wizard', '--setup-wizard', action='store_true',
                         help='set up URL, collection and optional login; save ./dq.ini or --config FILE; suggests dq-demo for an unset collection; blank username skips password')
    commands.add_argument('-h', '--help', action='help',
                          help='show this help message and exit')

    target_options.add_argument(
        "--config",
        metavar="FILE",
        help="file to read, create, or update; default: ./dq.ini in the current working directory; if absent, searches parent directories",
    )
    target_options.add_argument(
        "--main_url",
        "--main-url",
        metavar="URL",
        help="server base URL, optionally including the collection or index",
    )
    target_options.add_argument(
        "--collection",
        "--index",
        metavar="NAME",
        help="collection or index name (--index is a synonym)",
    )
    target_options.add_argument(
        "--list_fields",
        "--list-fields",
        action="store_true",
        help="list Solr collection fields and their schema properties",
    )
    target_options.add_argument('--username', metavar='NAME', help='HTTP Basic authentication username')
    target_options.add_argument('--password', metavar='PASSWORD',
                        help='HTTP Basic password; prefer the INI file to shell history')
    target_options.add_argument('--reports_dir', '--reports-dir', metavar='DIR',
                        help='Markdown and CSV output directory; created automatically; default: reports/ in cwd; overrides INI reports_dir')
    target_options.add_argument('--rows', '--size', dest='rows', metavar='N', type=row_limit,
                        help='synonyms: maximum documents to check per scan; accepts 1_000; default: -1 (no limit); 0 skips scans; overrides INI rows; presence counts stay collection-wide')
    target_options.add_argument('--trust_certificate', '--trust-certificate', metavar='FILE',
                        help='optional PEM for self-signed/private-CA certificates not already trusted; not needed for normal HTTPS')

    field_options.add_argument(
        "--include_fields",
        "--include_field",
        "--include-fields",
        "--include-field",
        metavar="PATTERN",
        action="append",
        nargs="+",
        default=[],
        help="include one or more simple glob patterns; repeatable; overrides INI include_fields; use '' to clear",
    )
    field_options.add_argument(
        "--exclude_fields",
        "--exclude_field",
        "--exclude-fields",
        "--exclude-field",
        metavar="PATTERN",
        action="append",
        nargs="+",
        default=[],
        help="exclude one or more simple glob patterns; repeatable; overrides INI exclude_fields; use '' to clear",
    )
    output_options.add_argument('--skip_null_values', '--skip-null-values', nargs='?', const=True, type=boolean_option, metavar='BOOL',
                        help='omit nulls/missing records from standard_text and shared regex/checkup text checks; retain empty strings and whitespace; default: false; use false to override INI true')
    output_options.add_argument('--progress_every', '--progress-every', metavar='N', type=progress_interval,
                        help='one flushed progress dot per N source documents; default: 1000; 0 disables dots; accepts 1_000; overrides INI progress_every')
    return parser



def resolve_selection(options, parser):
    """Keep record-selection rules separate from special report names."""
    for name in ('include_fields', 'exclude_fields'):
        groups = getattr(options, name)
        setattr(options, name, [pattern for group in groups for pattern in group])
    rules = [name for group in options.rule for name in group]
    reports = [name for group in options.report for name in group]
    utilities = sum(bool(value) for value in (options.list_fields, options.list_reports,
                                              options.list_rules, options.write_config,
                                              options.config_wizard))
    if utilities > 1 or (utilities and (rules or reports or options.action)):
        parser.error('choose a rule/action pair, a special report, or one utility command: --list_fields, --list_reports, --list_rules, --write_config, or --config_wizard')
    if reports and (rules or options.action == 'csv'):
        parser.error('special reports choose their own checks; use --report NAME, or --rule NAME --action csv')
    if rules and options.action == 'report':
        parser.error('rules export findings with --action csv; use --report NAME for a special report')
    options.rule_source = 'command line --rule/--rules'
    options.action_source = 'command line --action'
    if reports:
        if options.action is None:
            options.action_source = 'implied by --report/--reports'
        options.action = 'report'
    options.rule = []
    for name in rules:
        if name not in options.rule:
            options.rule.append(name)
    options.report = []
    for name in reports:
        if name not in options.report:
            options.report.append(name)
