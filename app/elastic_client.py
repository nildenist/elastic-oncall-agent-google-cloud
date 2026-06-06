from typing import Any, Dict, List

from elasticsearch import Elasticsearch, helpers

from app.config import get_settings
from app.demo_data import get_demo_documents


INDEX_NAMES = [
    "logs-app",
    "metrics-service",
    "alerts",
    "deploy-events",
    "runbooks",
    "incidents-history",
    "agent-results",
]


def get_elastic_client() -> Elasticsearch:
    settings = get_settings()

    if not settings.elastic_url or not settings.elastic_api_key:
        raise RuntimeError(
            "ELASTIC_URL and ELASTIC_API_KEY must be configured in .env or environment variables."
        )

    return Elasticsearch(
        settings.elastic_url,
        api_key=settings.elastic_api_key,
        request_timeout=30,
    )


def ensure_indices(client: Elasticsearch) -> None:
    for index_name in INDEX_NAMES:
        if not client.indices.exists(index=index_name):
            client.indices.create(index=index_name)


def seed_demo_data(client: Elasticsearch) -> Dict[str, Any]:
    ensure_indices(client)

    docs_by_index = get_demo_documents()
    actions = []

    for index_name, docs in docs_by_index.items():
        for doc in docs:
            actions.append(
                {
                    "_index": index_name,
                    "_source": doc,
                }
            )

    success_count, errors = helpers.bulk(
        client,
        actions,
        refresh=True,
        raise_on_error=False,
    )

    return {
        "inserted": success_count,
        "errors": errors,
        "indices": list(docs_by_index.keys()),
    }


def search_recent_logs(
    client: Elasticsearch,
    service: str,
    environment: str = "prod",
    size: int = 10,
) -> List[Dict[str, Any]]:
    response = client.search(
        index="logs-app",
        size=size,
        sort=[{"@timestamp": {"order": "desc"}}],
        query={
            "bool": {
                "must": [
                    {"term": {"service.keyword": service}},
                    {"term": {"environment.keyword": environment}},
                ]
            }
        },
    )
    return [hit["_source"] for hit in response["hits"]["hits"]]


def search_related_logs(
    client: Elasticsearch,
    query_text: str,
    size: int = 10,
) -> List[Dict[str, Any]]:
    response = client.search(
        index="logs-app",
        size=size,
        query={
            "multi_match": {
                "query": query_text,
                "fields": ["message", "service", "level"],
            }
        },
    )
    return [hit["_source"] for hit in response["hits"]["hits"]]


def get_service_metrics(
    client: Elasticsearch,
    service: str,
    size: int = 20,
) -> List[Dict[str, Any]]:
    response = client.search(
        index="metrics-service",
        size=size,
        sort=[{"@timestamp": {"order": "asc"}}],
        query={"term": {"service.keyword": service}},
    )
    return [hit["_source"] for hit in response["hits"]["hits"]]


def get_recent_deploys(
    client: Elasticsearch,
    service: str,
    size: int = 5,
) -> List[Dict[str, Any]]:
    response = client.search(
        index="deploy-events",
        size=size,
        sort=[{"@timestamp": {"order": "desc"}}],
        query={"term": {"service.keyword": service}},
    )
    return [hit["_source"] for hit in response["hits"]["hits"]]


def search_runbooks_and_incidents(
    client: Elasticsearch,
    query_text: str,
    size: int = 5,
) -> Dict[str, List[Dict[str, Any]]]:
    runbooks = client.search(
        index="runbooks",
        size=size,
        query={
            "multi_match": {
                "query": query_text,
                "fields": ["title", "content", "recommended_action", "service"],
            }
        },
    )

    incidents = client.search(
        index="incidents-history",
        size=size,
        query={
            "multi_match": {
                "query": query_text,
                "fields": ["title", "summary", "resolution", "service"],
            }
        },
    )

    return {
        "runbooks": [hit["_source"] for hit in runbooks["hits"]["hits"]],
        "incidents": [hit["_source"] for hit in incidents["hits"]["hits"]],
    }


def save_incident_brief(
    client: Elasticsearch,
    incident_brief: Dict[str, Any],
) -> Dict[str, Any]:
    response = client.index(
        index="agent-results",
        document=incident_brief,
        refresh=True,
    )
    return {
        "result": response.get("result"),
        "id": response.get("_id"),
    }


def get_latest_incident_brief(client: Elasticsearch) -> Dict[str, Any] | None:
    response = client.search(
        index="agent-results",
        size=1,
        sort=[{"created_at": {"order": "desc"}}],
        query={"match_all": {}},
    )

    hits = response["hits"]["hits"]
    if not hits:
        return None

    return hits[0]["_source"]
