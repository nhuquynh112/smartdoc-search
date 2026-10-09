"""Select reproducible news samples and export UTF-8 TXT without changing the DB."""
import argparse
import csv
import hashlib
import json
import random
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from smartdoc.config import PROJECT_ROOT

CATEGORIES = ['Khoa học công nghệ','Giáo dục','Sức khỏe','Kinh doanh','Thể thao']
DATASET_URL = 'https://huggingface.co/datasets/VLUS06/VietOnlineNews'

def normalize(value):
    return ' '.join(unicodedata.normalize('NFC', value or '').split())

def select_rows(path, per_category=40, seed=20261009):
    csv.field_size_limit(10000000)
    groups = {c: [] for c in CATEGORIES}
    seen_ids, seen_text = set(), set()
    skipped = Counter()
    with path.open(encoding='utf-8-sig',newline='') as f:
        reader = csv.DictReader(f)
        if not {'id','title','content','category'}.issubset(reader.fieldnames or []):
            raise ValueError('Expected id, title, content and category columns.')
        for row in reader:
            category = normalize(row['category'])
            if category not in groups: continue
            title, content = normalize(row['title']), normalize(row['content'])
            article_id = row['id'].strip()
            if not article_id.isdigit() or not title or not content:
                skipped['invalid_or_empty'] += 1; continue
            if len(content.split()) < 100 or len(content.split()) > 5000:
                skipped['length_filter'] += 1; continue
            fingerprint = hashlib.sha256(content.casefold().encode('utf-8')).hexdigest()
            if article_id in seen_ids or fingerprint in seen_text:
                skipped['duplicate'] += 1; continue
            seen_ids.add(article_id); seen_text.add(fingerprint)
            groups[category].append({'dataset_id':article_id,'title':title,'content':content,'category':category})
    selected = []
    rng = random.Random(seed)
    for category in CATEGORIES:
        eligible = sorted(groups[category],key=lambda r:int(r['dataset_id']))
        if len(eligible) < per_category: raise ValueError(f'Not enough eligible articles: {category}')
        selected.extend(sorted(rng.sample(eligible,per_category),key=lambda r:int(r['dataset_id'])))
    return selected, dict(skipped)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=PROJECT_ROOT/'data/raw/vietonline_news/dev.csv')
    parser.add_argument('--output',type=Path,default=PROJECT_ROOT/'data/raw/vietonline_news/selected_200')
    parser.add_argument('--per-category',type=int,default=40)
    parser.add_argument('--seed',type=int,default=20261009)
    args=parser.parse_args()
    if args.per_category < 1: parser.error('--per-category must be positive.')
    if args.output.exists(): parser.error('Output already exists. Use a new output folder to avoid overwriting a corpus.')
    rows, skipped = select_rows(args.input,args.per_category,args.seed)
    source_hash=hashlib.sha256()
    with args.input.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): source_hash.update(chunk)
    args.output.mkdir(parents=True)
    manifest_rows=[]
    for row in rows:
        filename=f"news_{row['dataset_id']}.txt"
        payload=(row['title']+'\n\n'+row['content']+'\n').encode('utf-8')
        (args.output/filename).write_bytes(payload)
        manifest_rows.append({'filename':filename,'dataset_id':row['dataset_id'],'title':row['title'],
                              'category':row['category'],'source_uri':DATASET_URL,
                              'sha256':hashlib.sha256(payload).hexdigest()})
    with (args.output/'sources.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(manifest_rows[0]),lineterminator='\n')
        w.writeheader();w.writerows(manifest_rows)
    manifest={'dataset':'VLUS06/VietOnlineNews','split':'dev','dataset_url':DATASET_URL,
              'input_sha256':source_hash.hexdigest(),'seed':args.seed,'per_category':args.per_category,
              'categories':CATEGORIES,'document_count':len(rows),'skipped':skipped,
              'filters':{'min_content_whitespace_words':100,'max_content_whitespace_words':5000},
              'generated_at_utc':datetime.now(timezone.utc).isoformat(),
              'source_note':'Dataset-level provenance; original article URLs are unavailable in this CSV.',
              'documents':manifest_rows}
    (args.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Prepared {len(rows)} TXT documents; {args.per_category} per category.')
    print(f'Output: {args.output}')
    print('Database unchanged. Review samples before ingestion.')

if __name__=='__main__':main()
