"""Persistent request/result state with direct, filtered cosine retrieval."""
from datetime import datetime, timezone
import json
import re
from uuid import UUID

from psycopg.types.json import Jsonb
from .models import INSUFFICIENT, vector_literal


class InvalidRequest(ValueError):
    """A structurally valid message that does not match persistent work."""


def validate_request(message, message_id, correlation_id):
    expected = {'schemaVersion', 'type', 'requestId', 'correlationId', 'question', 'productId', 'deadline'}
    if set(message) != expected or message['schemaVersion'] != 1 or message['type'] != 'chat.request':
        raise ValueError('Unsupported request schema')
    for key in ('requestId', 'correlationId'):
        UUID(message[key])
    if message['productId'] is not None:
        UUID(message['productId'])
    if message['requestId'] != str(message_id) or message['correlationId'] != str(correlation_id):
        raise ValueError('Message headers do not match the persistent identifiers')
    if not isinstance(message['question'], str) or not 1 <= len(message['question'].strip()) <= 1000:
        raise ValueError('Question must be 1..1000 characters')
    if datetime.fromisoformat(message['deadline'].replace('Z', '+00:00')).tzinfo is None:
        raise ValueError('Deadline requires a timezone')
    return message


def reply(message, status='completed', answer='', sources=None, error=None):
    return dict(schemaVersion=1, type='chat.reply', requestId=message['requestId'],
                correlationId=message['correlationId'], status=status,
                answer=answer, sources=sources or [], errorCode=error)


def retrieve(connection, embedding, product_id=None, count=3, min_similarity=0.35):
    if not 1 <= count <= 8:
        raise ValueError('Retrieval count must be 1..8')
    literal = vector_literal(embedding)
    rows = connection.execute('''SELECT p.id,p.name,c.manual_id,c.chunk_index,c.content,
           1 - (c.embedding <=> %s::vector) AS similarity
        FROM manual_chunks c JOIN products p ON p.id=c.product_id
        WHERE p.status='ready' AND (%s::uuid IS NULL OR p.id=%s::uuid)
        AND 1 - (c.embedding <=> %s::vector) >= %s
        ORDER BY c.embedding <=> %s::vector, c.manual_id, c.chunk_index LIMIT %s''',
        (literal, product_id, product_id, literal, min_similarity, literal, count)).fetchall()
    return [dict(reference=index + 1, productId=str(row[0]), productName=row[1], manualId=str(row[2]),
                 chunkIndex=row[3], excerpt=row[4], similarity=float(row[5])) for index, row in enumerate(rows)]


def process_question(connection, message, model, count=3, min_similarity=0.35):
    key = message['requestId']
    if not connection.execute('SELECT pg_try_advisory_lock(hashtextextended(%s, 1))', (key,)).fetchone()[0]:
        raise RuntimeError('Request is in progress on another worker; retry')
    try:
        row = connection.execute('''SELECT correlation_id,question,product_id,status,deadline
                                    FROM chat_requests WHERE id=%s''', (key,)).fetchone()
        if (not row or str(row[0]) != message['correlationId'] or row[1] != message['question']
                or (str(row[2]) if row[2] else None) != message['productId']):
            raise InvalidRequest('Message does not match the stored request')
        cached = connection.execute('SELECT payload FROM chat_results WHERE request_id=%s', (key,)).fetchone()
        if cached:
            return cached[0]
        if row[4] <= datetime.now(timezone.utc) or row[3] == 'failed':
            result = reply(message, 'failed', error='request_timeout')
        else:
            connection.execute("UPDATE chat_requests SET status='processing',updated_at=now() WHERE id=%s AND status='queued'", (key,))
            sources = retrieve(connection, model.embed([message['question']])[0], message['productId'], count, min_similarity)
            answer = model.answer(message['question'], sources) if sources else INSUFFICIENT
            citations = {int(value) for value in re.findall(r'\[(\d+)\]', answer)}
            selected = [source for source in sources if source['reference'] in citations]
            if not selected:
                answer = INSUFFICIENT
            result = reply(message, answer=answer, sources=selected)
        cache_reply(connection, result)
        return result
    finally:
        connection.execute('SELECT pg_advisory_unlock(hashtextextended(%s, 1))', (key,))


def cache_reply(connection, result):
    connection.execute('''INSERT INTO chat_results(request_id,correlation_id,payload) VALUES (%s,%s,%s)
                          ON CONFLICT(request_id) DO NOTHING''',
                       (result['requestId'], result['correlationId'], Jsonb(result)))


def apply_reply(connection, result):
    """Same guarded SQL as Products; used to exercise the protocol with real PG."""
    return connection.execute('''UPDATE chat_requests SET status=%s,answer=%s,sources=%s,error=%s,updated_at=now()
        WHERE id=%s AND correlation_id=%s AND status IN ('queued','processing') AND deadline>now()''',
        (result['status'], result['answer'], Jsonb(result['sources']), result['errorCode'],
         result['requestId'], result['correlationId'])).rowcount
