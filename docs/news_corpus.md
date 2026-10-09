# News Corpus Import

Prepare `dev.csv` using `python -m scripts.prepare_news_corpus`. The seed, CSV checksum, dataset IDs, categories and per-file hashes are recorded in the generated manifest. Source URLs identify the dataset, not the original publishers' article URLs. Sharing terms are unresolved; generated article text is not committed.

```bash
python -m scripts.init_db
python -m scripts.ingest_news_manifest
python -m scripts.export_corpus --corpus vietonline_news_200 --output reports/tv2_news_corpus.json
```

The manifest importer verifies all file hashes before DB changes and preserves article titles, category, dataset ID and dataset source reference. Existing integration records retain `corpus_name=integration`; nothing is deleted. Each article commits independently, so failed runs may be partially complete. Matching duplicates are skipped when rerunning; incompatible duplicate metadata requires explicit resolution.

For TV2 live integration, call `load_corpus_snapshot('vietonline_news_200')`. Default snapshot loading includes all ready documents, so always select this corpus for the news experiment. Corpus revision is global and can increase on changes to other corpora; extra rebuilds are conservative. JSON exports contain `corpus_name`, `preprocessing`, `corpus_revision`, and the filtered records. Keep the selected corpus label with index artifacts.

The 200 articles are a candidate evaluation corpus; manual review, query design and relevance judgments are still required. News category labels do not define query relevance.
