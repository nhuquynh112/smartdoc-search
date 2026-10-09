"""Read-only corpus checks; these do not certify linguistic extraction quality."""
from collections import Counter
from hashlib import sha256
from urllib.parse import urlparse


def inspect_document(row, storage):
    result = dict(row)
    result['source_status'] = ('missing' if not row.get('source_uri') else
        'web' if urlparse(row['source_uri']).scheme in {'http', 'https'} else 'non_web')
    issues = []
    result['observed_token_count'] = None
    if row['ingest_status'] == 'ready':
        for field in ['storage_ref', 'text_ref']:
            ref = row.get(field)
            if not ref:
                issues.append(f'{field}:missing_reference'); continue
            try:
                path = storage.resolve(ref)
                if field == 'storage_ref':
                    payload = path.read_bytes()
                    if len(payload) != row['size_bytes']: issues.append('original:size_mismatch')
                    if sha256(payload).hexdigest() != row['sha256']: issues.append('original:hash_mismatch')
                else:
                    text = path.read_text(encoding='utf-8')
                    result['observed_token_count'] = len(text.split())
                    if not text.strip(): issues.append('processed:empty')
                    if '\ufffd' in text: issues.append('processed:replacement_character')
            except (OSError, ValueError, UnicodeError) as exc:
                issues.append(f'{field}:{type(exc).__name__}')
    result['storage_check'] = ('not_checked' if row['ingest_status'] != 'ready' else 'issues' if issues else 'passed')
    result['quality_issues'] = '; '.join(issues)
    return result


def summarize(rows, revision):
    ready = [r for r in rows if r['ingest_status'] == 'ready']
    total_words = sum(r.get('word_count') or 0 for r in ready)
    return {
        'corpus_revision': revision,
        'total_records': len(rows),
        'status_counts': dict(Counter(r['ingest_status'] for r in rows)),
        'ready_documents': len(ready),
        'ready_file_types': dict(Counter(r['file_type'] for r in ready)),
        'total_word_count_before_stopwords': total_words,
        'mean_word_count_before_stopwords': round(total_words / len(ready), 2) if ready else 0,
        'ready_missing_source': sum(r['source_status'] == 'missing' for r in ready),
        'ready_non_web_source': sum(r['source_status'] == 'non_web' for r in ready),
        'ready_storage_issues': sum(r['storage_check'] == 'issues' for r in ready),
        'duplicate_upload_count': None,
        'limitations': [
            'Duplicate upload attempts are not persisted; their count is unavailable.',
            'Storage checks do not establish correct PDF reading order or Vietnamese text quality.',
            'Source status reflects database metadata, not data/sources.csv.',
            'Observed token count is after stopword removal; stored word_count is before removal.',
        ],
    }
