"""Validate JSON and GraphQL syntax in maintained repository files."""

import json
import os
from pathlib import Path

from graphql import GraphQLError, parse
from line_length import EXCLUDED_DIRECTORIES


def check_source_formats(root):
    failed = False
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [d for d in subdirectories if d not in EXCLUDED_DIRECTORIES]
        for name in files:
            path = Path(directory) / name
            if path.suffix not in (".json", ".graphql"):
                continue
            try:
                text = path.read_text(encoding="utf-8")
                if path.suffix == ".json":
                    json.loads(text)
                else:
                    parse(text)
            except (ValueError, GraphQLError) as error:
                print(f"{path}: {error}")
                failed = True
    return int(failed)
