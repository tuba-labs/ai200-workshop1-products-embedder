"""Event Grid-backed Blob trigger. The host fetches the blob using identity."""
from functools import lru_cache
import logging
import re

import azure.functions as func
from rag_core.config import load_settings
from rag_core.embedding import index_manual
from rag_core.models import AzureModels

app = func.FunctionApp()


@lru_cache(maxsize=1)
def dependencies():
    settings = load_settings()
    return settings, AzureModels(settings)


@app.function_name(name='IndexManual')
@app.blob_trigger(arg_name='manual', path='manuals/products/{productId}/{manualId}.txt',
                  connection='ManualStorage', source='EventGrid')
def index(manual: func.InputStream):
    match = re.search(r'products/([0-9a-f-]{36})/([0-9a-f-]{36})\.txt$', manual.name or '')
    if not match:
        raise ValueError('Blob path must identify an immutable product and manual')
    settings, model = dependencies()
    data = manual.read()
    if len(data) > 131072:
        raise ValueError('Manual exceeds the 128 KiB workshop limit')
    with settings.connect() as connection:
        result = index_manual(connection, *match.groups(), data, model,
                              settings.values['embedding-deployment'], settings.integer('chunk-size', 200, 2000))
    logging.info('manual=%s duplicate=%s chunks=%s', match.group(2), result['duplicate'], result['chunks'])
