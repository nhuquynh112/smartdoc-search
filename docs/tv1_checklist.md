# TV1 Delivery Checklist

Status reviewed on 12 October 2026 on the local integrated `Dat` checkout.
Evidence: `reports/data_quality_summary.json`, `reports/tv3_integration.json`
and the disposable-database suite. Historical evidence remains in the TV3
acceptance record; checks below do not certify the instructor's unconfirmed
storage requirement or permission to redistribute the dataset.

## Repository and Environment

- [x] Create the repository structure and English README.
- [x] Exclude local credentials, uploaded documents and generated artifacts from Git.
- [ ] Confirm the instructor's feed storage requirement.
- [x] Configure PostgreSQL and verify a database connection.
- [x] Record and verify Python dependencies (`requirements_tv3.txt` for the integrated app).

## Data and Ingestion

- [ ] Complete the integration source register in `data/sources.csv` (some sources/dates remain blank). News provenance is recorded separately in the generated news manifest and DB; these identify the dataset, not original publisher URLs.
- [ ] Prepare ten permitted integration documents.
- [x] Implement TXT and PDF text extraction.
- [x] Implement shared Vietnamese preprocessing.
- [x] Generate metadata and SHA-256 fingerprints automatically.
- [x] Handle duplicate, empty, unreadable and no-text documents in automated tests. A real scanned PDF remains a manual acceptance case.
- [x] Store original files and processed text before marking documents ready.
- [x] Verify persisted storage references: 200 ready TXT originals and caches pass hash/size/content checks on this machine, 12 October 2026.

## Integration and Delivery

- [x] Implement the indexing data contract using ready documents only.
- [x] Verify stable IDs and deterministic ordering with TV2.
- [x] Coordinate corpus revision changes and index rebuilds with TV2.
- [x] Collect at least 100 documents and summarize structural data quality (200 ready; linguistic/manual relevance review remains separate).
- [x] Document schema, preprocessing decisions and ingestion failures.
- [ ] Verify the setup instructions from a fresh environment.
