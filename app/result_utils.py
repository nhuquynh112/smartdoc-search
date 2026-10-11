"""Portable CSV export for an already freshness-checked ranked response."""
from __future__ import annotations

import csv
from io import StringIO


def _spreadsheet_text(value: object) -> str:
    text = str(value if value is not None else "")
    # CSV quoting alone does not prevent spreadsheet formula execution.
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def ranked_results_csv(recorded: dict) -> bytes:
    """Keep engine order and precision; UTF-8 BOM supports Vietnamese in Excel.

    The caller must verify freshness before offering the download. A snapshot
    export records its version so it remains identifiable after a later rebuild.
    """
    response = recorded["response"]
    if response.get("status") != "ok":
        raise ValueError("Only a successful ranked response can be exported.")
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["query", "top_k", "index_version", "corpus_revision", "rank",
                     "document_id", "title", "source_uri", "cosine_score"])
    for doc in response["results"]:
        writer.writerow([
            _spreadsheet_text(recorded["query"]), recorded["top_k"],
            _spreadsheet_text(response.get("index_version")), response.get("corpus_revision"),
            doc["rank"], doc["document_id"], _spreadsheet_text(doc.get("title")),
            _spreadsheet_text(doc.get("source_uri")), format(float(doc["score"]), ".17g"),
        ])
    return output.getvalue().encode("utf-8-sig")
