"""Immutable manuals, database-visible processing state and atomic indexing."""
import hashlib
from uuid import UUID

from .chunks import chunk_text
from .models import vector_literal


def index_manual(connection, product_id, manual_id, data, model, deployment, chunk_size=900):
    product_id, manual_id = UUID(str(product_id)), UUID(str(manual_id))
    key = str(manual_id)
    locked = connection.execute('SELECT pg_try_advisory_lock(hashtextextended(%s, 0))', (key,)).fetchone()[0]
    if not locked:
        raise RuntimeError('Manual is already being indexed; retry this event later')
    try:
        row = connection.execute('SELECT manual_sha256, status FROM products WHERE id=%s AND manual_id=%s',
                                 (product_id, manual_id)).fetchone()
        if not row:
            raise ValueError('No product record for this blob; upload through Products first')
        if hashlib.sha256(data).hexdigest() != row[0]:
            raise ValueError('Immutable manual checksum mismatch; upload a new product instead of replacing its blob')
        if row[1] == 'ready':
            return {'duplicate': True, 'chunks': 0}
        connection.execute("UPDATE products SET status='processing', error=NULL, updated_at=now() WHERE id=%s", (product_id,))
        try:
            parts = chunk_text(data.decode('utf-8-sig'), chunk_size)
            # Keep each Azure request comfortably below the service's input limits.
            embeddings = []
            for offset in range(0, len(parts), 16):
                embeddings.extend(model.embed(parts[offset:offset + 16]))
            if len(embeddings) != len(parts):
                raise ValueError('Embedding count mismatch')
            values = [vector_literal(vector) for vector in embeddings]
            with connection.transaction():
                connection.execute('DELETE FROM manual_chunks WHERE manual_id=%s', (manual_id,))
                with connection.cursor() as cursor:
                    cursor.executemany('''INSERT INTO manual_chunks
                        (manual_id,product_id,chunk_index,content,embedding,embedding_deployment)
                        VALUES (%s,%s,%s,%s,%s::vector,%s)''',
                        [(manual_id, product_id, index, part, value, deployment)
                         for index, (part, value) in enumerate(zip(parts, values, strict=True))])
                connection.execute("UPDATE products SET status='ready', error=NULL, updated_at=now() WHERE id=%s", (product_id,))
            return {'duplicate': False, 'chunks': len(parts)}
        except Exception:
            # Persist an actionable, non-secret error; the original exception is
            # raised so the Functions extension can retry and finally poison it.
            connection.execute("UPDATE products SET status='failed', error=%s, updated_at=now() WHERE id=%s",
                               ('Indexing failed. Check Function logs and blob-trigger poison queue; retry the immutable blob.', product_id))
            raise
    finally:
        connection.execute('SELECT pg_advisory_unlock(hashtextextended(%s, 0))', (key,))
