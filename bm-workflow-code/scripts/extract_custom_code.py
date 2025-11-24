#!/usr/bin/env python3
"""
Discover HubSpot workflows that use Custom Code actions and extract their source.

Usage:
    python scripts/extract_custom_code.py workflows/ --csv-out custom-code.csv --json-out custom-code.json --code-dir workflow_code
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract custom code actions from HubSpot workflow exports.")
    parser.add_argument(
        "targets",
        nargs="+",
        type=Path,
        help="Workflow JSON files or directories containing them.",
    )
    parser.add_argument("--csv-out", type=Path, default=None, help="Optional CSV summary output path.")
    parser.add_argument("--json-out", type=Path, default=None, help="Optional JSON output path (includes code).")
    parser.add_argument("--code-dir", type=Path, default=None, help="Directory to write extracted source files.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    return parser.parse_args()


def configure_logging(verbose: bool) -> None:
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def resolve_targets(targets: Iterable[Path]) -> List[Path]:
    files: List[Path] = []
    for target in targets:
        if target.is_dir():
            for candidate in target.rglob("*.json"):
                if candidate.is_file():
                    files.append(candidate)
        elif target.is_file() and target.suffix.lower() == ".json":
            files.append(target)
        else:
            logging.warning("Skipping %s (not a JSON file or directory)", target)
    if not files:
        raise FileNotFoundError("No workflow JSON files found.")
    return sorted(files)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def iter_workflows(payload) -> Iterator[Dict]:
    if isinstance(payload, dict):
        if "workflows" in payload and isinstance(payload["workflows"], list):
            for wf in payload["workflows"]:
                if isinstance(wf, dict):
                    yield wf
        else:
            yield payload
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item


def find_actions(node) -> Iterator[Dict]:
    if isinstance(node, dict):
        if {"actionId", "type"} <= node.keys():
            yield node
        for value in node.values():
            yield from find_actions(value)
    elif isinstance(node, list):
        for element in node:
            yield from find_actions(element)


def is_custom_code(action: Dict) -> bool:
    type_val = str(action.get("type", "")).upper()
    action_type = str(action.get("actionType", "")).upper()
    if "CUSTOM_CODE" in type_val or "CUSTOM_CODE" in action_type:
        return True
    if "customCodeAction" in action or "customCode" in action:
        return True
    return False


def slugify(value: str, fallback: str = "item") -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or fallback


def detect_language(action: Dict) -> Optional[str]:
    candidates = [
        action.get("language"),
        action.get("runtime"),
        action.get("customCodeAction", {}).get("language"),
        action.get("customCode", {}).get("language"),
        action.get("config", {}).get("language"),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None


def detect_runtime(action: Dict) -> Optional[str]:
    candidates = [
        action.get("runtime"),
        action.get("customCodeAction", {}).get("runtime"),
        action.get("customCode", {}).get("runtime"),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None


def extract_code(action: Dict) -> Optional[str]:
    candidates = [
        action.get("source"),
        action.get("code"),
        action.get("functionSource"),
        action.get("customCodeAction", {}).get("sourceCode"),
        action.get("customCode", {}).get("source"),
        action.get("config", {}).get("sourceCode"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return None


def extract_list(value) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, dict):
        return [f"{k}={v}" for k, v in value.items()]
    if value:
        return [str(value)]
    return []


def write_code_file(
    base_dir: Path,
    workflow_name: str,
    action_name: str,
    language: Optional[str],
    code: str,
) -> Path:
    ext = ".js"
    if language and "python" in language.lower():
        ext = ".py"
    wf_slug = slugify(workflow_name or "workflow")
    action_slug = slugify(action_name or "action")
    dest = base_dir / wf_slug / f"{action_slug}{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as fp:
        fp.write(code)
    return dest


def process_workflow(path: Path, workflow: Dict, code_dir: Optional[Path]) -> List[Dict]:
    records: List[Dict] = []
    workflow_name = workflow.get("name") or workflow.get("label") or "Unnamed Workflow"
    workflow_id = workflow.get("id") or workflow.get("workflowId")

    for action in find_actions(workflow):
        if not is_custom_code(action):
            continue

        language = detect_language(action)
        runtime = detect_runtime(action)
        code = extract_code(action)
        secrets = extract_list(
            action.get("secrets")
            or action.get("customCodeAction", {}).get("secrets")
            or action.get("customCode", {}).get("secrets")
        )
        inputs = extract_list(
            action.get("inputFields")
            or action.get("customCodeAction", {}).get("inputFields")
            or action.get("customCode", {}).get("inputFields")
        )

        code_path = None
        code_hash = None
        if code:
            code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
            if code_dir:
                code_path = write_code_file(code_dir, workflow_name, action.get("name", ""), language, code)

        record = {
            "workflow_name": workflow_name,
            "workflow_id": workflow_id,
            "workflow_file": str(path),
            "action_name": action.get("name"),
            "action_id": action.get("actionId") or action.get("id"),
            "action_type": action.get("type") or action.get("actionType"),
            "language": language,
            "runtime": runtime,
            "code": code,
            "code_hash": code_hash,
            "code_path": str(code_path) if code_path else None,
            "secrets": secrets,
            "inputs": inputs,
        }
        records.append(record)
    return records


def write_csv(records: Iterable[Dict], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "workflow_name",
        "workflow_id",
        "workflow_file",
        "action_name",
        "action_id",
        "action_type",
        "language",
        "runtime",
        "code_path",
        "code_hash",
        "secrets",
        "inputs",
    ]
    with destination.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = record.copy()
            row["secrets"] = ";".join(record.get("secrets", []))
            row["inputs"] = ";".join(record.get("inputs", []))
            row.pop("code", None)
            writer.writerow(row)


def write_json(records: Iterable[Dict], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as fp:
        json.dump(list(records), fp, indent=2)


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)
    files = resolve_targets(args.targets)

    all_records: List[Dict] = []
    for file_path in files:
        payload = load_json(file_path)
        for workflow in iter_workflows(payload):
            records = process_workflow(file_path, workflow, args.code_dir)
            all_records.extend(records)
            if records:
                logging.info(
                    "Found %d custom code actions in %s (%s)",
                    len(records),
                    workflow.get("name"),
                    file_path,
                )

    if args.csv_out:
        write_csv(all_records, args.csv_out)
    if args.json_out:
        write_json(all_records, args.json_out)

    logging.info("Processed %d workflows; %d custom code actions", len(files), len(all_records))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

