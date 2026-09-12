"""Configuration discovery and target URL construction for DQ."""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit


class ConfigError(ValueError):
    """The DQ configuration is missing or invalid."""


@dataclass(frozen=True)
class DqConfig:
    main_url: str | None = None
    collection: str | None = None
    source: Path | None = None


def _project_config(start: Path) -> Path | None:
    directory = start.resolve()
    for candidate_directory in (directory, *directory.parents):
        candidate = candidate_directory / "dq.ini"
        if candidate.is_file():
            return candidate
    return None


def _read_config(path: Path) -> DqConfig:
    parser = configparser.ConfigParser()
    try:
        with path.open(encoding="utf-8") as stream:
            parser.read_file(stream)
    except (OSError, configparser.Error) as error:
        raise ConfigError(f"could not read configuration {path}: {error}") from error

    values = dict(parser.defaults())
    if parser.has_section("dq"):
        values.update(parser["dq"])
    return DqConfig(
        main_url=values.get("main_url"),
        collection=values.get("collection"),
        source=path,
    )


def load_config(explicit_path: str | None = None, start: Path | None = None) -> DqConfig:
    """Load explicit, project, or user configuration and apply environment values."""
    path: Path | None
    if explicit_path:
        path = Path(explicit_path).expanduser()
        if not path.is_file():
            raise ConfigError(f"configuration file does not exist: {path}")
    else:
        path = _project_config(start or Path.cwd())
        if path is None:
            user_path = Path.home() / ".config" / "dq" / "config.ini"
            path = user_path if user_path.is_file() else None

    config = _read_config(path) if path else DqConfig()
    if explicit_path:
        return config
    return DqConfig(
        main_url=os.environ.get("DQ_MAIN_URL", config.main_url),
        collection=os.environ.get("DQ_COLLECTION", config.collection),
        source=config.source,
    )


def collection_url(
    config: DqConfig,
    *,
    main_url: str | None = None,
    collection: str | None = None,
) -> str:
    """Resolve a complete collection URL from command-line and saved values."""
    resolved_main_url = main_url or config.main_url
    if not resolved_main_url:
        raise ConfigError(
            "main_url is required; use --main_url, DQ_MAIN_URL, or a dq.ini file"
        )
    normalized_url = resolved_main_url.rstrip("/")
    path_parts = [unquote(part) for part in urlsplit(normalized_url).path.split("/") if part]
    has_collection_path = bool(path_parts) and path_parts != ["solr"]
    if has_collection_path:
        collection_was_also_declared = collection is not None or (
            main_url is None and config.collection is not None
        )
        if collection_was_also_declared:
            raise ConfigError(
                "main_url already includes a collection or index; remove "
                "--collection/--index or the collection setting from dq.ini"
            )
        return normalized_url

    resolved_collection = collection or config.collection
    if not resolved_collection:
        raise ConfigError(
            "collection is not present in main_url; use --collection, "
            "DQ_COLLECTION, or a dq.ini file"
        )
    collection_path = quote(resolved_collection.strip("/"), safe="")
    return f"{normalized_url}/{collection_path}"


def main_url_has_collection(main_url: str) -> bool:
    """Return whether a URL path appears to include a collection or index."""
    path_parts = [unquote(part) for part in urlsplit(main_url.rstrip("/")).path.split("/") if part]
    return bool(path_parts) and path_parts != ["solr"]


def write_config(path: Path, main_url: str, collection: str | None) -> None:
    """Atomically update target settings, commenting out changed old values."""
    normalized_main_url = main_url.rstrip("/")
    previous = _read_config(path) if path.is_file() else DqConfig()

    lines = ["[DEFAULT]"]
    if previous.main_url and previous.main_url != normalized_main_url:
        lines.append(f"# Previous main_url = {previous.main_url}")
    lines.append(f"main_url = {normalized_main_url}")

    if previous.collection and previous.collection != collection:
        lines.append(f"# Previous collection = {previous.collection}")
    if collection:
        lines.append(f"collection = {collection}")
    contents = "\n".join(lines) + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
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
        raise ConfigError(f"could not write configuration {path}: {error}") from error
