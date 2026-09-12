"""Markdown report generation for DQ."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from dq.field_selection import DEFAULT_EXCLUDED_FIELDS, select_fields
from dq.solr import collection_document_count, list_fields


class ReportError(RuntimeError):
    """A report could not be written."""


def _format_patterns(patterns: Sequence[str]) -> str:
    return ", ".join(
        "`" + pattern.replace("`", "\\`") + "`" for pattern in patterns
    )


def _code(value: str) -> str:
    value = value.replace("\n", " ")
    return f"`` {value} ``" if "`" in value else f"`{value}`"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    """Render pipe tables with columns padded for reading the Markdown source."""
    cells = [
        [cell.replace("\r", " ").replace("\n", " ").replace("|", "\\|") for cell in row]
        for row in [headers, *rows]
    ]
    widths = [max(3, *(len(row[i]) for row in cells)) for i in range(len(headers))]

    def render(row: Sequence[str]) -> str:
        return "| " + " | ".join(cell.ljust(width) for cell, width in zip(row, widths)) + " |"

    return [render(cells[0]), render(["-" * width for width in widths]),
            *(render(row) for row in cells[1:])]


def _write_text(path: Path, contents: str) -> None:
    temporary_path = path.with_name(f".{path.name}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8") as stream:
            stream.write(contents)
        temporary_path.replace(path)
    except OSError as error:
        try:
            temporary_path.unlink()
        except OSError:
            pass
        raise ReportError(f"could not write report {path}: {error}") from error


def write_empty_fields_report(
    collection_url: str,
    output_path: Path,
    *,
    include: Sequence[str] = (),
    exclude: Sequence[str] = (),
    configuration_path: Path | None = None,
    configuration_explicit: bool = False,
    option_details: Sequence[tuple[str, str, str]] = (),
) -> None:
    """Write a Markdown report for stored fields missing from some documents."""
    total_documents = collection_document_count(collection_url)
    selected = select_fields(
        list_fields(collection_url),
        include=include,
        exclude=exclude,
    )
    stored_fields = [field for field in selected if field.get("stored") is True]
    effective_exclude = exclude if include or exclude else DEFAULT_EXCLUDED_FIELDS
    incomplete = []
    for field in stored_fields:
        populated = int(field["documents"])
        missing = max(total_documents - populated, 0)
        if missing:
            incomplete.append((field, populated, missing))

    lines = [
        "# Empty Fields Report",
        "",
        "- [Summary](#summary)",
        "- [Options Used](#options-used)",
        "- [Fields](#fields)",
        "",
        "## Summary",
        "",
        f"- Collection: `{collection_url}`",
        *(
            [
                f"- Configuration: `{configuration_path}` "
                f"({'specified by `--config`' if configuration_explicit else 'default configuration'})"
            ]
            if configuration_path is not None
            else []
        ),
        f"- Collection documents: {total_documents:,}",
        f"- Include field patterns: {_format_patterns(include) if include else 'all fields'}",
        f"- Exclude field patterns: "
        f"{_format_patterns(effective_exclude) if effective_exclude else 'none'}",
        f"- Stored fields checked: {len(stored_fields):,}",
        f"- Incomplete stored fields: {len(incomplete):,}",
        "",
        "## Options Used",
        "",
        *_table(
            ("Option", "Value", "Source"),
            [(_code(name), _code(value), source) for name, value, source in option_details],
        ),
        "",
        "## Fields",
        "",
    ]
    if incomplete:
        rows = []
        for field, populated, missing in incomplete:
            percentage = (populated / total_documents * 100) if total_documents else 0.0
            rows.append((
                _code(str(field.get('name', ''))),
                _code(str(field.get('type', ''))),
                f"{populated:,}", f"{missing:,}", f"{percentage:.2f}%",
            ))
        lines.extend(_table(
            ("Field", "Type", "Documents with a value", "Missing documents", "Populated"),
            rows,
        ))
    else:
        lines.append("All selected stored fields are populated in every document.")
    lines.extend(
        [
            "",
            "A missing value means Solr did not detect the field in that document. "
            "An indexed empty string may still count as present.",
            "",
        ]
    )
    _write_text(output_path, "\n".join(lines))
