# TV1 to TV2 Corpus Handoff

## Export on TV1's machine

With PostgreSQL running and the virtual environment activated:

```bash
python -m scripts.export_corpus --corpus vietonline_news_200 --output reports/tv2_news_corpus.json
```

Output: `reports/tv2_news_corpus.json`. This generated file is ignored by Git. Share it with the team through an agreed file-sharing channel; cloning the repository does not retrieve it. Do not publish source text without checking sharing permissions.

The export contains processed text and metadata for ready documents, stable IDs, the corpus revision and a snapshot fingerprint. It is not a database backup and does not contain original PDFs. Storage references refer to TV1's storage and will not resolve on another machine unless those files are transferred separately.

## Use on TV2's machine without PostgreSQL

Install project requirements in a virtual environment and obtain the exported JSON. Load the records directly:

```python
import json
from pathlib import Path

snapshot = json.loads(Path('reports/tv2_news_corpus.json').read_text(encoding='utf-8'))
documents = snapshot['documents']
document_ids = [doc['document_id'] for doc in documents]
texts = [doc['clean_text'] for doc in documents]
```

The texts are already preprocessed. Do not segment them again. Preserve the IDs in matrix row order; they are not necessarily consecutive.

For an initial unigram baseline:

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from smartdoc.preprocessing import preprocess_text

vectorizer = TfidfVectorizer(
    tokenizer=str.split,
    token_pattern=None,
    preprocessor=None,
    lowercase=False,
    norm='l2',
    smooth_idf=True,
    sublinear_tf=False,
)
X = vectorizer.fit_transform(texts)
q = vectorizer.transform([preprocess_text('ứng dụng trí tuệ nhân tạo')])
```

This is integration guidance, not the completed TV2 engine. Build an inverted index using the fitted features, select the union of query postings, calculate cosine, and verify against full-corpus scoring. Save document IDs and corpus revision with the index artifacts.

## Live integration

When running against TV1's database/storage on the same machine, use `smartdoc.ingestion.load_corpus_snapshot("vietonline_news_200")` to obtain documents and revision together. An exported snapshot supports offline algorithm development, not a live freshness check against TV1's changing corpus.

## Current limitations

- The corpus contains 200 news articles across five categories; relevance queries and labels still need to be created.
- Source references identify the dataset. Original publisher article URLs are not provided by the downloaded CSV.
- Per-document manifests are recorded and snapshot loading rejects unknown or outdated processing. See `preprocessing_version.md`; save the snapshot preprocessing fingerprint with index artifacts and compare it with the query pipeline.
- Extraction quality and tokenization require manual review; successful export does not certify linguistic accuracy.
- A database copy is sufficient for raw-text viewing; original-file download still requires the storage folder.

## PostgreSQL content storage

Live snapshot reads obtain clean text directly from `documents.clean_text`. Content viewing uses `raw_text`. Original file references still resolve against the local storage adapter. Upgrade existing DBs with `python -m scripts.init_db` followed by `python -m scripts.backfill_document_text`.
