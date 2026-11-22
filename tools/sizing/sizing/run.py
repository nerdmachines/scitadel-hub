"""S-013 sizing harness: fetch a fixed-seed OpenAlex sample, run the CPU text tier of the cascade,
count chunks, build a BM25 index and write aggregate numbers. Runs on ksb, keeps nothing
(see README). Network, third-party and process code lives here; the arithmetic is in core.py."""
import argparse
import concurrent.futures as cf
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

from . import core

UA = 'scitadel-hub-sizing/0.1 (+https://github.com/nerdmachines/scitadel-hub)'
FILTER = 'best_oa_location.license:cc-by|cc0|public-domain'
OA = 'https://api.openalex.org/works'
EPMC = 'https://www.ebi.ac.uk/europepmc/webservices/rest/{}/fullTextXML'
TOKENIZER = 'https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/resolve/main/tokenizer.json'
MAX_PDF = 100 * 2**20
# Published sizes of public files that cannot be read from a manifest (cited, dated).
PUBLISHED = {'crossref_public_data_file_2026_gb': 208, 'datacite_public_data_file_2025_gib': 33}
SOURCES = {'openalex_manifest': 'https://openalex.s3.amazonaws.com/data/{}/manifest.json',
           'crossref': 'https://crossref.org/blog/2026-public-data-file-now-available/',
           'datacite': 'https://datafiles.datacite.org/'}


class Blocked(Exception):
    pass


LOCK, NEXT, ROBOTS = threading.Lock(), {}, {}


def pace(host, interval):
    """At most one request per `interval` seconds to each host, across threads."""
    with LOCK:
        t = max(time.monotonic(), NEXT.get(host, 0))
        NEXT[host] = t + interval
    time.sleep(max(0, t - time.monotonic()))


def http(url, interval=1.0, cap=None, timeout=60):
    """GET with the declared User-Agent, per-host pacing and Retry-After; returns bytes."""
    host = urllib.parse.urlsplit(url).netloc
    for attempt in range(4):
        pace(host, interval)
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read(cap + 1 if cap else None)
                if cap and len(body) > cap:
                    raise ValueError('too_large')
                return body
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:  # 500 to 504: Europe PMC answers transient errors
                time.sleep(min(int(e.headers.get('Retry-After') or 5), 120))
                continue
            raise
    raise RuntimeError('unreachable')


def robots_ok(url):
    parts = urllib.parse.urlsplit(url)
    rp = ROBOTS.get(parts.netloc)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            rp.parse(http(f'{parts.scheme}://{parts.netloc}/robots.txt', 1.0, 2**20, 20).decode('utf-8', 'replace').splitlines())
        except Exception:
            rp.parse([])  # no readable robots.txt: nothing is disallowed
        ROBOTS[parts.netloc] = rp
    return rp.can_fetch('scitadel-hub-sizing', url)


def oa(params):
    key = os.environ.get('OPENALEX_API_KEY')
    q = dict(params, **({'api_key': key} if key else {}))
    try:
        return json.loads(http(f'{OA}?{urllib.parse.urlencode(q)}', 0.2))
    except urllib.error.HTTPError as e:
        if e.code in (401, 402, 403, 429):
            raise Blocked(f'needs OpenAlex API key: HTTP {e.code} {e.read()[:300]!r}')
        raise


def populations():
    """Two API calls: the count of the filter and its split by type; `papers` is the S-014 ruling (2026-11-22):
    the scholarly types article, review, preprint and conference-paper (`core.PAPER_TYPES`), the planning case."""
    out = {'all_types': oa({'filter': FILTER, 'per_page': 1, 'select': 'id'})['meta']['count']}
    out['by_type'] = {g['key'].rsplit('/', 1)[-1]: g['count'] for g in oa({'filter': FILTER, 'group_by': 'type'})['group_by']}
    out['article'] = out['by_type']['article']
    out['papers'] = sum(out['by_type'][t] for t in core.PAPER_TYPES)
    return out


def sample(seed, n=10000):
    recs = []
    for page in range(1, n // 100 + 1):
        recs += oa({'filter': FILTER, 'sample': n, 'seed': seed, 'per_page': 100, 'page': page})['results']
    return recs


def records_for(ids):
    recs = []
    for i in range(0, len(ids), 50):
        recs += oa({'filter': 'openalex_id:' + '|'.join(ids[i:i + 50]), 'per_page': 50})['results']
    return recs


def pdf_text(data, tmp):
    p = tmp / f'{threading.get_ident()}.pdf'
    p.write_bytes(data)
    try:
        r = subprocess.run(['pdftotext', '-enc', 'UTF-8', str(p), '-'], capture_output=True, timeout=300)
        return r.stdout.decode('utf-8', 'replace') if r.returncode == 0 else None
    except subprocess.TimeoutExpired:
        return None
    finally:
        p.unlink(missing_ok=True)


def process(rec, tok, tmp, zc):
    """Fetch and extract one work. Returns the measured row; text goes to tmp/text/<id>.txt."""
    wid = rec['id'].rsplit('/', 1)[-1]
    row = {'id': wid, 'type': rec.get('type'), 'source': core.source_of(rec), 'route': core.route_of(rec),
           'status': 'ok', 'pdf_bytes': 0, 'jats_zst_bytes': 0, 'refs': len(rec.get('referenced_works') or []),
           'meta_json_bytes': len(json.dumps(core.project(rec), separators=(',', ':')).encode())}
    paras = None
    if row['route'] == 'jats':
        try:
            xml = http(EPMC.format(core.pmcid_of(rec)), 0.2, MAX_PDF)
            paras = core.jats_paragraphs(xml)
            row['jats_zst_bytes'] = len(zc.compress(xml))
        except Exception:
            row['route'] = 'pdf' if (rec.get('best_oa_location') or {}).get('pdf_url') else 'unresolved'
            row['jats_miss'] = True
    if row['route'] == 'pdf':
        url = rec['best_oa_location']['pdf_url']
        try:
            if not robots_ok(url):
                row['status'] = 'robots'
            else:
                data = http(url, 1.0, MAX_PDF)
                if not data.startswith(b'%PDF'):
                    row['status'] = 'not_pdf'
                else:
                    row['pdf_bytes'] = len(data)
                    text = pdf_text(data, tmp)
                    paras = core.pdf_paragraphs(text) if text else None
                    row['status'] = 'ok' if paras else 'no_text'
        except Exception as e:
            row['status'] = 'fetch_' + type(e).__name__
    elif row['route'] == 'unresolved':
        row['status'] = 'unresolved'
    if paras:
        text = '\n'.join(paras).encode()
        counts = [len(e.ids) for e in tok.encode_batch(paras, add_special_tokens=False)]
        row.update(text_bytes=len(text), text_zst_bytes=len(zc.compress(text)), tokens=sum(counts))
        for t in core.CHUNK_TARGETS:
            row[f'chunks_{t}'] = core.count_chunks(counts, t)
        (tmp / 'text' / f'{wid}.txt').write_bytes(text)
    return row


def bm25_ratio(tmp, rounds, seed, ids=None):
    """tantivy index bytes / indexed text bytes of the works `ids` (default: all with text); the CI spans `rounds` random 80 %
    subsamples without replacement (resampling with replacement duplicates documents and shrinks the ratio)."""
    import random
    import tantivy
    files = sorted(f for f in (tmp / 'text').glob('*.txt') if ids is None or f.stem in ids)

    def build(sel, name):
        sb = tantivy.SchemaBuilder()
        sb.add_text_field('body', stored=False, tokenizer_name='en_stem', index_option='position')
        d = tmp / name
        d.mkdir()
        w = tantivy.Index(sb.build(), path=str(d)).writer(heap_size=2 * 2**30, num_threads=8)
        total = 0
        for f in sel:
            t = f.read_text()
            total += len(t.encode())
            w.add_document(tantivy.Document(body=t))
        w.commit()
        w.wait_merging_threads()
        size = sum(p.stat().st_size for p in d.rglob('*') if p.is_file())
        shutil.rmtree(d)
        return size / total
    full = build(files, 'idx-full')
    rng = random.Random(seed)
    draws = sorted(build(rng.sample(files, int(0.8 * len(files))), f'idx-b{i}') for i in range(rounds))
    return {'n': len(files), 'mean': full, 'median': full, 'p90': None,
            'ci95': [min(full, core.percentile(draws, 0.025)), max(full, core.percentile(draws, 0.975))], 'subsample_rounds': rounds}


def parquet_bytes(rows):
    import pyarrow as pa
    import pyarrow.parquet as pq
    buf = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows), buf, compression='zstd', compression_level=3)
    return buf.tell()


def factors(rows, meta_parquet, bm25):
    """Per-paper factors of a set of rows. Text-derived ones are over works that yielded text;
    byte and share factors are over every work, zero where they do not apply."""
    n, ok = len(rows), [r for r in rows if 'tokens' in r]
    f = {'pdf_share': core.summarize([float(r['route'] == 'pdf') for r in rows]),
         'jats_share': core.summarize([float(r['jats_zst_bytes'] > 0) for r in rows]),
         'unresolved_share': core.summarize([float(r['route'] == 'unresolved') for r in rows]),
         'fetch_failure_share': core.summarize([float(r['status'] not in ('ok', 'unresolved')) for r in rows]),
         'pdf_bytes': core.summarize(core.pdf_contributions(rows)),
         'jats_zst_bytes': core.summarize([r['jats_zst_bytes'] for r in rows]),
         'refs': core.summarize([r['refs'] for r in rows]),
         'meta_json_bytes': core.summarize([r['meta_json_bytes'] for r in rows]),
         'bm25_ratio': bm25}
    for k in ('text_bytes', 'text_zst_bytes', 'tokens', 'chunks_350', 'chunks_300', 'chunks_400'):
        f[k] = core.summarize([r[k] for r in ok])
    zero = core.summarize([r['pdf_bytes'] for r in rows])  # failures as 0: the imputed CI is narrower, so widen its lower end
    f['pdf_bytes']['ci95'][0] = min(f['pdf_bytes']['ci95'][0], zero['ci95'][0])
    pdf_only = [r for r in rows if r['route'] == 'pdf' and r['pdf_bytes']]
    f['pdf_bytes_per_pdf_only_work'] = core.summarize([r['pdf_bytes'] for r in pdf_only])
    f['meta_parquet_bytes'] = meta_parquet
    return f


def parquet_summary(projected):
    """Parquet bytes per work: the file of all rows is the mean; the 95 % bootstrap CI (1,000 rounds, as the other factors)
    is of the bytes per work of files of resampled rows. A resample repeats rows, which compresses better, so the
    interval sits below the mean; it is widened to include the mean (the exception stated in 2.4)."""
    lo, hi = core.bootstrap_ci(len(projected), lambda ix: parquet_bytes([projected[i] for i in ix]) / len(ix), rounds=1000)
    mean = parquet_bytes(projected) / len(projected)
    return {'n': len(projected), 'mean': mean, 'median': None, 'p90': None, 'ci95': [min(mean, lo), max(mean, hi)]}


def by_route(rows):
    """Text and chunk numbers per extraction route (JATS body text vs pdftotext output)."""
    out = {}
    for route in ('jats', 'pdf'):
        ok = [r for r in rows if r['route'] == route and 'tokens' in r]
        out[route] = {'works': sum(r['route'] == route for r in rows), **{k: core.summarize([r[k] for r in ok]) for k in ('text_bytes', 'chunks_350')}}
    return out


def snapshots():
    def one(f):
        m = json.loads(http(SOURCES['openalex_manifest'].format(f), 0.2, 2**30, 300))
        works = next(e for e in m['entities'] if e['entity'] == 'works')
        return {'date': m['date'], 'bytes': m['meta']['content_length'], 'works_records': works['record_count'], 'entities': {e['entity']: e['content_length'] for e in m['entities']}}
    out = {f'openalex_{f}': one(f) for f in ('jsonl', 'parquet')}
    out['published'] = dict(PUBLISHED, sources={k: v for k, v in SOURCES.items() if k != 'openalex_manifest'})
    return out


# The hub's generations are the scheduled quarterly releases (RELEASE_NOTES.txt: the second Wednesday of January, April, July and October), so the
# generation before 2026-10-14 is the scheduled one of 2026-07-08, though the notes list no release on that day (06-25, then 09-23). Its delta is the
# partitions updated since; the deltas since 09-23 and 06-25, the releases the notes do list, are in `tsra.json` too (S-015).
QUARTER_SINCE = '2026-07-08'


def bulk_tb(snap, tsra=None):
    """Bytes per generation (S-013: the hub keeps the whole OpenAlex snapshot it bootstraps from, jsonl in the low and central
    case, Parquet in the high one, plus the Crossref and DataCite files and the unmeasured rest) and, from S-015, the OpenAlex
    delta of a quarterly generation (`core.snapshot_bulk`). Without `tsra` the delta is the whole generation: no deduplication."""
    rest = PUBLISHED['crossref_public_data_file_2026_gb'] * 1e9 + PUBLISHED['datacite_public_data_file_2025_gib'] * 2**30 + core.MODEL['others_tb'] * core.TB
    man = {'jsonl': snap['openalex_jsonl']['bytes'], 'parquet': snap['openalex_parquet']['bytes']}
    delta = {f: tsra['snapshot_deltas']['formats'][f][QUARTER_SINCE]['delta'] for f in man} if tsra else man
    return core.snapshot_bulk(man, rest / core.TB, delta)


def extrapolations(result):
    """(Re)compute every basis's extrapolation from its measured factors; no network. The S-015 factors (`result['tsra']`) are
    the same for every basis: they were measured on the scholarly types."""
    pops, snap, tsra = result['population'], result['snapshots'], result.get('tsra')
    bulk = bulk_tb(snap, tsra)
    extra = core.tsra_factors(tsra) if tsra else {}
    for basis, b in result['bases'].items():
        b['extrapolation'] = core.extrapolate(pops[basis], {**b['factors'], **extra}, bulk)
    result['model_scope_7M'] = core.extrapolate(7e6, {**result['bases']['papers']['factors'], **extra}, bulk)  # the first model's central N, at the planning case's factors


def cmd_recompute(a):
    path = Path(a.measurements)
    result = json.loads(path.read_text())
    if a.tsra:
        result['tsra'] = json.loads(Path(a.tsra).read_text())
    if a.figures:  # the figure stage re-run: replaces the figures and the snapshot listing of the tables run
        fg = json.loads(Path(a.figures).read_text())
        result['tsra'].update(figures=fg['figures'], snapshot_deltas=fg['snapshot_deltas'], figures_run={k: fg[k] for k in ('status', 'routes', 'parameters')})
    extrapolations(result)
    path.write_text(json.dumps(result, indent=1) + '\n')


def tool_versions():
    import pyarrow, tantivy, tokenizers, zstandard
    pv = subprocess.run(['pdftotext', '-v'], capture_output=True, text=True).stderr.splitlines()[0]
    return {'python': sys.version.split()[0], 'tokenizers': tokenizers.__version__, 'pyarrow': pyarrow.__version__,
            'zstandard': zstandard.__version__, 'tantivy': getattr(tantivy, '__version__', None), 'pdftotext': pv, 'zstd_level': 3}


def cmd_run(a):
    import zstandard
    from tokenizers import Tokenizer
    out, tmp = Path(a.out), Path(a.scratch)
    (tmp / 'text').mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    pops = populations()
    if a.manifest:
        man = json.loads(Path(a.manifest).read_text())
        recs = records_for(man['work_ids'][:a.limit] if a.limit else man['work_ids'])
    else:
        recs = sample(a.seed)[:a.limit or None]
        man = core.manifest(recs, a.seed, FILTER, time.strftime('%Y-%m-%d'), pops)
        (out / 'manifest.json').write_text(core.dump_manifest(man))
    tok_bytes = http(TOKENIZER, 0.2, 2**28, 120)
    tok = Tokenizer.from_str(tok_bytes.decode())
    rows, done = [], set()
    res = out / 'results.jsonl'
    if res.exists():
        rows = [json.loads(line) for line in res.read_text().splitlines()]
        done = {r['id'] for r in rows}
    todo = [r for r in recs if r['id'].rsplit('/', 1)[-1] not in done]
    with cf.ThreadPoolExecutor(a.workers) as ex, res.open('a') as fh:
        for i, row in enumerate(ex.map(lambda r: process(r, tok, tmp, zstandard.ZstdCompressor(level=3)), todo)):
            fh.write(json.dumps(row) + '\n')
            fh.flush()
            rows.append(row)
            if i % 200 == 0:
                print(f'{len(rows)}/{len(recs)}', flush=True)
    projected = {r['id'].rsplit('/', 1)[-1]: core.project(r) for r in recs}
    snap = snapshots()
    result = {'parameters': {'seed': a.seed, 'filter': FILTER, 'chunk_targets': core.CHUNK_TARGETS, 'dims': core.MODEL['dims'],
                             'tokenizer': TOKENIZER, 'tokenizer_sha256': hashlib.sha256(tok_bytes).hexdigest(),
                             'tools': tool_versions(), 'sample_n': len(rows)},
              'population': pops, 'snapshots': snap, 'routes_actual': {k: sum(r['route'] == k for r in rows) for k in ('jats', 'pdf', 'unresolved')},
              'status': {k: sum(r['status'] == k for r in rows) for k in sorted({r['status'] for r in rows})}, 'bases': {}}
    for basis, sel in (('all_types', rows), ('papers', [r for r in rows if r['type'] in core.PAPER_TYPES]), ('article', [r for r in rows if r['type'] == 'article'])):
        meta = parquet_summary([projected[r['id']] for r in sel])
        bm25 = bm25_ratio(tmp, a.bootstrap_rounds, a.seed, {r['id'] for r in sel})  # per basis: the index of that basis's works
        result['bases'][basis] = {'n': len(sel), 'factors': factors(sel, meta, bm25)}
    result['by_route'] = by_route(rows)  # the sizes follow from `recompute --tsra`, which adds the S-015 factors
    (out / 'measurements.json').write_text(json.dumps(result, indent=1))
    shutil.rmtree(tmp / 'text', ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='sizing')
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run', help='sample, measure, aggregate')
    for flag, kw in (('--out', {'required': True}), ('--scratch', {'default': '/tmp/sizing-scratch'}), ('--seed', {'type': int, 'default': 83}),
                     ('--manifest', {}), ('--limit', {'type': int, 'default': 0}), ('--workers', {'type': int, 'default': 48}),
                     ('--bootstrap-rounds', {'type': int, 'default': 10})):
        r.add_argument(flag, **kw)
    r.set_defaults(fn=cmd_run)
    t = sub.add_parser('tsra', help='S-015: tessera footprint of the document model, figures and snapshot deltas')
    for flag, kw in (('--out', {'required': True}), ('--scratch', {'required': True}), ('--manifest', {'default': str(Path(__file__).resolve().parents[1] / 'data' / 'manifest.json')}), ('--seed', {'type': int, 'default': 83}),
                     ('--limit', {'type': int, 'default': 0}), ('--workers', {'type': int, 'default': 48}), ('--rounds', {'type': int, 'default': 10}), ('--records', {}), ('--stage', {'choices': ['tsra', 'figures'], 'default': 'tsra'}),
                     ('--release', {'default': '2026-10-14'}), ('--previous', {'nargs': '+', 'default': ['2026-09-23', '2026-07-08', '2026-06-25']}),
                     ('--tessera-commit', {'default': 'f390528eb2bfa3fc4ea474d9129c242b906e8e0a'})):
        t.add_argument(flag, **kw)
    t.set_defaults(fn=lambda a: __import__('sizing.s015', fromlist=['x']).cmd_tsra(a, tool_versions))
    rc = sub.add_parser('recompute', help='recompute extrapolations of a measurements.json in place')
    rc.add_argument('measurements')
    rc.add_argument('--figures', help='fold a figures.json (the S-015 figure stage) over the figures of the tsra.json')
    rc.add_argument('--tsra', help='fold a tsra.json (S-015) into the document before recomputing')
    rc.set_defaults(fn=cmd_recompute)
    a = ap.parse_args(argv)
    try:
        return a.fn(a) or 0
    except Blocked as e:
        print(f'BLOCKED: {e}')
        return 3


if __name__ == '__main__':
    sys.exit(main())
