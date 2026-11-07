import csv
from collections import Counter
from pathlib import Path

path=Path('data/evals/week15-user-trials.csv')
with path.open(encoding='utf-8-sig', newline='') as handle:
    reader=csv.DictReader(handle)
    reader.fieldnames=[name.lstrip('#').strip() for name in (reader.fieldnames or [])]
    rows=[{(key.lstrip('#').strip() if key else key): value for key, value in row.items()} for row in reader]
errors=Counter(r['error_type'] for r in rows if r.get('error_type'))
completed=sum(r.get('completed','').lower() in ('true','yes','1') for r in rows)
print({'participants':len({r['participant_id'] for r in rows if r.get('participant_id')}),'tasks':len(rows),'completed':completed,'errors':dict(errors)})

