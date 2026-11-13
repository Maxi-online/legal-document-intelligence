import os

broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

broker_connection_retry_on_startup = True

task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']
timezone = 'UTC'
enable_utc = True

task_routes = {
    'orchestrator.process_case_data': {'queue': 'processing'},
    'orchestrator.process_batch': {'queue': 'processing'},
    'context_extraction.extract_context': {'queue': 'processing'},
    'classification.classify_mention': {'queue': 'processing'},
    'ranking.rank_relevance': {'queue': 'processing'},
}

worker_prefetch_multiplier = 1
task_acks_late = True
