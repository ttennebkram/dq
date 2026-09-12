"""Small standard-library client for the Solr APIs used by DQ."""

from __future__ import annotations

import json
from fnmatch import fnmatchcase
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SolrError(RuntimeError):
    """A Solr request could not be completed."""


def get_json(collection_url: str, path: str, **parameters: object) -> dict[str, Any]:
    """Get a JSON response from an API below a Solr collection URL."""
    url = f"{collection_url.rstrip('/')}/{path.lstrip('/')}"
    if parameters:
        url = f"{url}?{urlencode(parameters)}"

    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        message = f"Solr returned HTTP {error.code} for {url}"
        if detail:
            message = f"{message}: {detail}"
        raise SolrError(message) from error
    except URLError as error:
        raise SolrError(f"Could not connect to {url}: {error.reason}") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise SolrError(f"Solr returned an invalid JSON response from {url}") from error


def field_document_count(collection_url: str, field_name: str) -> int:
    """Count documents containing a field, including point and vector fields."""
    response = get_json(
        collection_url,
        "select",
        q="*:*",
        fq="{!frange l=1}exists($dq_field)",
        dq_field=field_name,
        rows=0,
        wt="json",
    )
    result = response.get("response")
    count = result.get("numFound") if isinstance(result, dict) else None
    if not isinstance(count, int):
        raise SolrError(
            f"Solr response did not contain a document count for field {field_name!r}"
        )
    return count


def collection_document_count(collection_url: str) -> int:
    """Return the number of active documents in a collection."""
    response = get_json(collection_url, "select", q="*:*", rows=0, wt="json")
    result = response.get("response")
    count = result.get("numFound") if isinstance(result, dict) else None
    if not isinstance(count, int):
        raise SolrError("Solr response did not contain a collection document count")
    return count


def list_fields(collection_url: str) -> list[dict[str, Any]]:
    """Return concrete index fields enriched with their schema properties."""
    schema_response = get_json(
        collection_url,
        "schema/fields",
        includeDynamic="true",
        showDefaults="true",
        wt="json",
    )
    definitions = schema_response.get("fields")
    if not isinstance(definitions, list):
        raise SolrError("Solr Schema API response did not contain a fields list")

    luke_response = get_json(collection_url, "admin/luke", numTerms=0, wt="json")
    concrete_fields = luke_response.get("fields")
    if not isinstance(concrete_fields, dict):
        raise SolrError("Solr Luke API response did not contain a fields object")

    by_name = {str(field.get("name")): field for field in definitions}
    dynamic = [field for field in definitions if "*" in str(field.get("name", ""))]
    result: list[dict[str, Any]] = []
    for name, luke_properties in concrete_fields.items():
        definition = by_name.get(name)
        if definition is None:
            matches = [
                field
                for field in dynamic
                if fnmatchcase(name, str(field.get("name", "")))
            ]
            definition = max(
                matches,
                key=lambda field: len(str(field.get("name", "")).replace("*", "")),
                default={},
            )

        field = dict(definition)
        schema_name = str(field.get("name", ""))
        field["name"] = name
        field["schemaField"] = schema_name if schema_name != name else ""
        if isinstance(luke_properties, dict):
            field["documents"] = luke_properties.get("docs", "")
            field.setdefault("type", luke_properties.get("type", ""))
        if field.get("documents", "") == "":
            field["documents"] = field_document_count(collection_url, name)
        result.append(field)

    return sorted(result, key=lambda field: str(field.get("name", "")))
