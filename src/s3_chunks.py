import codecs

MIB = 1024 * 1024


def object_size(s3, bucket, key):
    return s3.head_object(Bucket=bucket, Key=key)["ContentLength"]


def iter_chunks(s3, bucket, key, chunk_bytes=16 * MIB):
    size = object_size(s3, bucket, key)
    dec = codecs.getincrementaldecoder("utf-8")(errors="strict")
    tail = ""
    cur = []
    quotes = 0
    start, idx = 0, 0
    while start < size:
        end = min(start + chunk_bytes, size) - 1
        body = s3.get_object(Bucket=bucket, Key=key, Range="bytes=%d-%d" % (start, end))["Body"].read()
        text = tail + dec.decode(body, final=(end == size - 1))
        lines = text.split("\n")
        tail = lines.pop()
        records = []
        for ln in lines:
            cur.append(ln)
            quotes += ln.count('"')
            if quotes % 2 == 0:
                records.append("\n".join(cur) + "\n")
                cur, quotes = [], 0
        if end == size - 1 and (tail or cur):
            cur.append(tail)
            records.append("\n".join(cur))
            tail, cur = "", []
        yield idx, records
        idx += 1
        start = end + 1