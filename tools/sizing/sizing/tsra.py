"""S-015: the document model as column tables, sized as tessera `.tsra` (written by tessera-py), as Parquet zstd (the
reference) and as raw Arrow bytes; vectors as Vortex fixed_size_list and as tessera arrays. Third-party code (pyarrow,
numpy, tessera, vortex) lives here; the arithmetic of the size model is in core.py."""
import io
import os
import random
import struct
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from . import core

TS = '2026-11-22T00:00:00Z'  # sealed into the product identity, so fixed
ARROW = {'u1': pa.uint8(), 'u2': pa.uint16(), 'u4': pa.uint32(), 'u8': pa.uint64(), 'i4': pa.int32(), 'f4': pa.float32(),
         'f8': pa.float64(), 'str': pa.string()}
BOX = [('x0', 'f4'), ('y0', 'f4'), ('x1', 'f4'), ('y1', 'f4')]
# The document-model blocks (docs/architecture/document-model.md section 1), every one sorted by (work_id, ord), and the
# metadata blocks of the kept OpenAlex fields. Group: meta (every work), doc (works with text), jats (JATS route only: PDF
# works need the T1 tier, #84, and are modelled at the JATS rate).
TABLES = {
    'works': ('meta', [('work_id', 'u8'), ('doi', 'str'), ('licence', 'str'), ('source', 'str'), ('extractor', 'str'), ('content_hash', 'str'),
                       ('input_hash', 'str'), ('input_url', 'str'), ('qc_elements', 'u4'), ('qc_tokens', 'u4'), ('qc_chars', 'u4'), ('tier', 'u1'),
                       ('type', 'str'), ('title', 'str'), ('year', 'u2'), ('language', 'str'), ('cited_by', 'u4'), ('venue', 'u8')]),
    'authorships': ('meta', [('work_id', 'u8'), ('ord', 'u2'), ('author', 'u8'), ('name', 'str'), ('institution', 'u8')]),
    'citations': ('meta', [('work_id', 'u8'), ('target', 'u8')]),
    'elements': ('doc', [('work_id', 'u8'), ('ord', 'u4'), ('parent_ord', 'i4'), ('kind', 'str'), ('text', 'str'), ('page', 'u2')] + BOX),
    'chunks': ('doc', [('work_id', 'u8'), ('chunk_id', 'u4'), ('first_ord', 'u4'), ('last_ord', 'u4'), ('tokens', 'u2')]),
    'figures': ('doc', [('work_id', 'u8'), ('fig_id', 'str'), ('caption_ord', 'i4'), ('page', 'u2')] + BOX + [('blob_ref', 'u8'), ('blob_bytes', 'u4')]),
    'table_cells': ('jats', [('work_id', 'u8'), ('table_id', 'u2'), ('row', 'u2'), ('col', 'u2'), ('text', 'str'), ('num', 'f8'), ('unit', 'str')]),
    'inline_refs': ('jats', [('work_id', 'u8'), ('ord', 'u4'), ('start', 'u4'), ('end', 'u4'), ('kind', 'str'), ('target', 'str')]),
    'bib': ('jats', [('work_id', 'u8'), ('bib_id', 'str'), ('title', 'str'), ('authors', 'str'), ('year', 'str'), ('doi', 'str'), ('matched_work_id', 'u8')]),
}


def arrow_table(cols, rows):
    """Arrow table from a column spec and row tuples."""
    cols_ = list(zip(*rows)) if rows else [()] * len(cols)
    return pa.table({n: pa.array(list(v), type=ARROW[t]) for (n, t), v in zip(cols, cols_)})


def tsra_columns(tbl, cols):
    """Arrow table -> tessera `(name, code, little-endian bytes)` columns; strings are `[u32 len | bytes]*`."""
    out = []
    for n, code in cols:
        a = tbl[n]
        if code == 'str':
            enc = [s.encode() for s in a.to_pylist()]
            out.append((n, 'str', b''.join(struct.pack('<I', len(e)) + e for e in enc)))
        else:
            out.append((n, code, np.asarray(a.to_numpy(), dtype='<' + code).tobytes()))
    return out


def write_tsra(path, name, blocks):
    """One tessera `table` product of the blocks `{name: (cols, arrow table)}`; returns the file size."""
    import tessera
    b = tessera.Builder('table', name, 'S-015 sizing', TS)
    for bn, (cols, tbl) in blocks.items():
        b.add_table(bn, tsra_columns(tbl, cols))
    b.pack(str(path))
    return os.path.getsize(path)


def parquet_bytes(tbl):
    buf = io.BytesIO()
    pq.write_table(tbl, buf, compression='zstd', compression_level=3)
    return buf.tell()


def measure(tbl, cols, tmp, name='t'):
    """Bytes of one table: tessera .tsra (one product), Parquet zstd, raw Arrow; plus rows."""
    return {'rows': tbl.num_rows, 'tsra': write_tsra(Path(tmp) / f'{name}.tsra', name, {name: (cols, tbl)}),
            'parquet_zstd': parquet_bytes(tbl), 'raw': tbl.nbytes}


def measure_tables(rows_by_table, tmp, n_works):
    """Per table: bytes of the whole sample as one block, per work (`n_works`), and of the `elements.text` column alone."""
    out = {}
    for name, (grp, cols) in TABLES.items():
        tbl = arrow_table(cols, rows_by_table[name])
        out[name] = {'group': grp, **measure(tbl, cols, tmp, name)}
        if name == 'elements':
            tcols = [c for c in cols if c[0] == 'text']
            out['elements.text'] = {'group': grp, **measure(tbl.select(['text']), tcols, tmp, 'text')}
    return out


def shard_range(rows_by_table, tmp, ids, flags, rounds, seed):
    """Tessera bytes per paper (`core.per_paper`) of ten random 80 % subsets of the works, as the BM25 range of S-013 (a resample with
    replacement would repeat rows and compress better). `flags` is work_id -> (has text, JATS with text); rows are keyed by column 0."""
    rng, out = random.Random(seed), []
    for i in range(rounds):
        keep = set(rng.sample(ids, int(0.8 * len(ids))))
        g = {}
        for name, (grp, cols) in TABLES.items():
            sub = arrow_table(cols, [r for r in rows_by_table[name] if r[0] in keep])
            g[grp] = g.get(grp, 0) + measure(sub, cols, tmp, f'r{i}-{name}')['tsra']
            if name == 'elements':
                g['text'] = measure(sub.select(['text']), [c for c in cols if c[0] == 'text'], tmp, f'r{i}-text')['tsra']
        out.append(core.per_paper(g, len(keep), sum(flags[k][0] for k in keep), sum(flags[k][1] for k in keep)))
    return out


def vector_bytes(dims, n, tmp, seed=83):
    """Encoded bytes per vector of synthetic unit vectors (a size measurement: embeddings barely compress, so the values
    do not matter, their entropy does): fp16 and int8 (one byte per dimension and a 4-byte scale) as a Vortex
    fixed_size_list (what the plan stores), as a tessera array block (what tessera writes today), and as Parquet zstd."""
    import tessera
    import vortex as vx
    rng = np.random.default_rng(seed)
    v = rng.standard_normal((n, dims)).astype(np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    f16 = v.astype('<f2')
    scale = np.abs(v).max(axis=1) / 127
    i8 = np.round(v / scale[:, None]).astype(np.int8)
    tmp = Path(tmp)
    ids = np.arange(n, dtype='<u8')

    def fsl(values, typ):
        return pa.FixedSizeListArray.from_arrays(pa.array(values.reshape(-1), type=typ), dims)

    def vortex(name, tbl):
        vx.io.write(vx.array(tbl), str(tmp / name))
        return os.path.getsize(tmp / name)

    def tarray(name, code, arr):
        b = tessera.Builder('table', name, 'S-015 sizing', TS)
        b.add_array('vec', code, list(arr.shape), arr.tobytes())
        b.pack(str(tmp / name))
        return os.path.getsize(tmp / name)
    t16 = pa.table({'work_id': ids, 'v': fsl(f16, pa.float16())})
    t8 = pa.table({'work_id': ids, 'v': fsl(i8, pa.int8()), 'scale': scale.astype('<f4')})
    raw16, raw8 = n * dims * 2, n * (dims + 4)
    res = {'dims': dims, 'n': n, 'raw_bytes_per_vector': {'fp16': raw16 / n, 'int8': raw8 / n},
           'vortex_fsl': {'fp16': vortex('v16.vortex', t16), 'int8': vortex('v8.vortex', t8)},
           'tessera_array': {'fp16': tarray('v16.tsra', 'f2', f16), 'int8': tarray('v8.tsra', 'i1', i8)},
           'parquet_zstd': {'fp16': parquet_bytes(t16), 'int8': parquet_bytes(t8)}}
    res['tessera_array']['int8'] += write_tsra(tmp / 'sc.tsra', 'sc', {'scale': ([('scale', 'f4')], pa.table({'scale': scale.astype('<f4')}))})
    for k in ('vortex_fsl', 'tessera_array', 'parquet_zstd'):
        res[k] = {c: {'bytes_per_vector': b / n, 'ratio_to_raw': b / (raw16 if c == 'fp16' else raw8)} for c, b in res[k].items()}
    return res


def overhead(tmp):
    """Fixed bytes of a tessera product (manifest, seal) against the same one-row table as a Vortex file: what a
    block written through tessera costs beyond its Vortex payload."""
    import vortex as vx
    tbl = arrow_table([('work_id', 'u8')], [(1,)])
    vx.io.write(vx.array(tbl), str(Path(tmp) / 'o.vortex'))
    t = write_tsra(Path(tmp) / 'o.tsra', 'o', {'o': ([('work_id', 'u8')], tbl)})
    return {'tsra_product_one_row': t, 'vortex_file_one_row': os.path.getsize(Path(tmp) / 'o.vortex')}


def blob_file(blobs, tmp, name='b.vortex'):
    """A Vortex file with one binary column of the figure blobs (tessera tables have no binary column, #issue)."""
    import vortex as vx
    tbl = pa.table({'blob_ref': np.arange(len(blobs), dtype='<u8'), 'bytes': pa.array(blobs, type=pa.large_binary())})
    vx.io.write(vx.array(tbl), str(Path(tmp) / name))
    return os.path.getsize(Path(tmp) / name)
