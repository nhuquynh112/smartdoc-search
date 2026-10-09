# TV1 Delivery Checklist

## Repository and Environment

- [x] Create the repository structure and English README.
- [x] Exclude local credentials, uploaded documents and generated artifacts from Git.
- [ ] Confirm the instructor's feed storage requirement.
- [ ] Configure PostgreSQL and verify a database connection.
- [ ] Record and verify Python dependencies.

## Data and Ingestion

- [ ] Register sources in `data/sources.csv`.
- [ ] Prepare ten permitted integration documents.
- [ ] Implement TXT and PDF text extraction.
- [ ] Implement shared Vietnamese preprocessing.
- [ ] Generate metadata and SHA-256 fingerprints automatically.
- [ ] Handle duplicate, empty, unreadable and image-only documents.
- [ ] Store original files and processed text before marking documents ready.
- [ ] Verify storage references after restarting the program.

## Integration and Delivery

- [ ] Implement the indexing data contract using ready documents only.
- [ ] Verify stable IDs and deterministic ordering with TV2.
- [ ] Coordinate corpus revision changes and index rebuilds with TV2.
- [ ] Collect at least 100 valid documents and summarize data quality.
- [ ] Document schema, preprocessing decisions and ingestion failures.
- [ ] Verify the setup instructions from a fresh environment.
