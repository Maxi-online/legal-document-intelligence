# Runtime and configuration

Review `docker-compose.yml` and the service-specific requirements before starting the full system. `settings.json.example` describes local configuration structure; populated settings and credentials stay outside Git. Run `python scripts/prepare_config.py` to generate missing configuration copies. The synthetic source generator can be exercised without PostgreSQL, Redis, Celery or a live document source; the complete UI/API workflow requires those services.

Use the component navigation and validation boundaries in the root [README](../README.md). Runtime services and external providers are not started by the offline replay.
