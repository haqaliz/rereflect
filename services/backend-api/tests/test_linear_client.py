"""
TDD tests for Linear GraphQL API client.

All HTTP calls are mocked — no real Linear API is needed.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
ACCESS_TOKEN = "lin_api_test_token_abc123"

MOCK_ORG_RESPONSE = {
    "data": {
        "organization": {
            "id": "org-uuid-1",
            "name": "Acme Corp",
            "urlKey": "acme",
        }
    }
}

MOCK_TEAMS_RESPONSE = {
    "data": {
        "teams": {
            "nodes": [
                {"id": "team-uuid-1", "name": "Engineering", "key": "ENG"},
                {"id": "team-uuid-2", "name": "Product", "key": "PRD"},
            ]
        }
    }
}

MOCK_PROJECTS_RESPONSE = {
    "data": {
        "team": {
            "projects": {
                "nodes": [
                    {"id": "proj-uuid-1", "name": "Q1 Roadmap"},
                    {"id": "proj-uuid-2", "name": "Bug Fixes"},
                ]
            }
        }
    }
}

MOCK_LABELS_RESPONSE = {
    "data": {
        "issueLabels": {
            "nodes": [
                {"id": "label-uuid-1", "name": "bug", "color": "#ff0000"},
                {"id": "label-uuid-2", "name": "feature", "color": "#00ff00"},
            ]
        }
    }
}

MOCK_WORKFLOW_STATES_RESPONSE = {
    "data": {
        "workflowStates": {
            "nodes": [
                {"id": "state-uuid-1", "name": "Backlog", "type": "backlog"},
                {"id": "state-uuid-2", "name": "In Progress", "type": "started"},
                {"id": "state-uuid-3", "name": "Done", "type": "completed"},
            ]
        }
    }
}

MOCK_CREATE_ISSUE_RESPONSE = {
    "data": {
        "issueCreate": {
            "success": True,
            "issue": {
                "id": "issue-uuid-123",
                "identifier": "ENG-142",
                "url": "https://linear.app/acme/issue/ENG-142/fix-csv-export",
                "title": "Fix CSV export timeout",
                "state": {"name": "Backlog", "type": "backlog"},
                "priority": 2,
                "assignee": None,
            }
        }
    }
}

MOCK_CREATE_WEBHOOK_RESPONSE = {
    "data": {
        "webhookCreate": {
            "success": True,
            "webhook": {
                "id": "webhook-uuid-1",
                "url": "https://rereflect.app/api/v1/webhooks/linear/inbound",
                "secret": "wh_secret_abc",
                "enabled": True,
            }
        }
    }
}

MOCK_DELETE_WEBHOOK_RESPONSE = {
    "data": {
        "webhookDelete": {
            "success": True,
        }
    }
}


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------
class TestLinearClientImport:

    def test_importable(self):
        from src.services.linear_client import LinearClient
        assert LinearClient is not None

    def test_instantiable(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)
        assert client is not None

    def test_stores_access_token(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)
        assert client.access_token == ACCESS_TOKEN

    def test_graphql_endpoint(self):
        from src.services.linear_client import LinearClient
        assert LinearClient.GRAPHQL_URL == "https://api.linear.app/graphql"


# ---------------------------------------------------------------------------
# get_organization
# ---------------------------------------------------------------------------
class TestGetOrganization:

    @pytest.mark.asyncio
    async def test_get_organization_returns_dict(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=MOCK_ORG_RESPONSE):
            result = await client.get_organization()

        assert result["id"] == "org-uuid-1"
        assert result["name"] == "Acme Corp"
        assert result["urlKey"] == "acme"

    @pytest.mark.asyncio
    async def test_get_organization_calls_graphql(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=MOCK_ORG_RESPONSE) as mock_post:
            await client.get_organization()

        mock_post.assert_called_once()
        query = mock_post.call_args[0][0]
        assert "organization" in query


# ---------------------------------------------------------------------------
# get_teams
# ---------------------------------------------------------------------------
class TestGetTeams:

    @pytest.mark.asyncio
    async def test_get_teams_returns_list(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=MOCK_TEAMS_RESPONSE):
            result = await client.get_teams()

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == "team-uuid-1"
        assert result[0]["name"] == "Engineering"

    @pytest.mark.asyncio
    async def test_get_teams_calls_graphql(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=MOCK_TEAMS_RESPONSE) as mock_post:
            await client.get_teams()

        mock_post.assert_called_once()
        query = mock_post.call_args[0][0]
        assert "teams" in query


# ---------------------------------------------------------------------------
# get_projects
# ---------------------------------------------------------------------------
class TestGetProjects:

    @pytest.mark.asyncio
    async def test_get_projects_returns_list(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=MOCK_PROJECTS_RESPONSE):
            result = await client.get_projects(team_id="team-uuid-1")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == "proj-uuid-1"
        assert result[0]["name"] == "Q1 Roadmap"

    @pytest.mark.asyncio
    async def test_get_projects_passes_team_id(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=MOCK_PROJECTS_RESPONSE) as mock_post:
            await client.get_projects(team_id="team-uuid-1")

        mock_post.assert_called_once()
        assert "team-uuid-1" in str(mock_post.call_args)


# ---------------------------------------------------------------------------
# get_labels
# ---------------------------------------------------------------------------
class TestGetLabels:

    @pytest.mark.asyncio
    async def test_get_labels_returns_list(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=MOCK_LABELS_RESPONSE):
            result = await client.get_labels()

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "bug"

    @pytest.mark.asyncio
    async def test_get_labels_calls_graphql(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=MOCK_LABELS_RESPONSE) as mock_post:
            await client.get_labels()

        mock_post.assert_called_once()
        query = mock_post.call_args[0][0]
        assert "issueLabels" in query


# ---------------------------------------------------------------------------
# get_workflow_states
# ---------------------------------------------------------------------------
class TestGetWorkflowStates:

    @pytest.mark.asyncio
    async def test_get_workflow_states_returns_list(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=MOCK_WORKFLOW_STATES_RESPONSE):
            result = await client.get_workflow_states(team_id="team-uuid-1")

        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0]["type"] == "backlog"
        assert result[2]["type"] == "completed"

    @pytest.mark.asyncio
    async def test_get_workflow_states_passes_team_id(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=MOCK_WORKFLOW_STATES_RESPONSE) as mock_post:
            await client.get_workflow_states(team_id="team-uuid-1")

        mock_post.assert_called_once()
        assert "team-uuid-1" in str(mock_post.call_args)


# ---------------------------------------------------------------------------
# create_issue
# ---------------------------------------------------------------------------
class TestCreateIssue:

    @pytest.mark.asyncio
    async def test_create_issue_returns_dict(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        issue_input = {
            "teamId": "team-uuid-1",
            "title": "Fix CSV export timeout",
            "description": "## Summary\n\nMultiple customers report...",
            "priority": 2,
        }

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=MOCK_CREATE_ISSUE_RESPONSE):
            result = await client.create_issue(input=issue_input)

        assert result["id"] == "issue-uuid-123"
        assert result["identifier"] == "ENG-142"
        assert result["url"] == "https://linear.app/acme/issue/ENG-142/fix-csv-export"
        assert result["title"] == "Fix CSV export timeout"

    @pytest.mark.asyncio
    async def test_create_issue_calls_mutation(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        issue_input = {"teamId": "team-uuid-1", "title": "Test Issue"}

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=MOCK_CREATE_ISSUE_RESPONSE) as mock_post:
            await client.create_issue(input=issue_input)

        mock_post.assert_called_once()
        query = mock_post.call_args[0][0]
        assert "issueCreate" in query
        assert "mutation" in query.lower()

    @pytest.mark.asyncio
    async def test_create_issue_raises_on_failure(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        failure_response = {
            "data": {
                "issueCreate": {
                    "success": False,
                    "issue": None,
                }
            }
        }

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=failure_response):
            with pytest.raises(Exception) as exc_info:
                await client.create_issue(input={"teamId": "t1", "title": "Fail"})

        assert exc_info.value is not None


# ---------------------------------------------------------------------------
# create_webhook
# ---------------------------------------------------------------------------
class TestCreateWebhook:

    @pytest.mark.asyncio
    async def test_create_webhook_returns_dict(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=MOCK_CREATE_WEBHOOK_RESPONSE):
            result = await client.create_webhook(
                url="https://rereflect.app/api/v1/webhooks/linear/inbound",
                team_id=None,
                secret="wh_secret_abc",
            )

        assert result["id"] == "webhook-uuid-1"
        assert result["url"] == "https://rereflect.app/api/v1/webhooks/linear/inbound"

    @pytest.mark.asyncio
    async def test_create_webhook_calls_mutation(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=MOCK_CREATE_WEBHOOK_RESPONSE) as mock_post:
            await client.create_webhook(url="https://example.com/hook", team_id=None, secret="secret")

        mock_post.assert_called_once()
        query = mock_post.call_args[0][0]
        assert "webhookCreate" in query
        assert "mutation" in query.lower()

    @pytest.mark.asyncio
    async def test_create_webhook_raises_on_failure(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        failure_response = {
            "data": {
                "webhookCreate": {
                    "success": False,
                    "webhook": None,
                }
            }
        }

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=failure_response):
            with pytest.raises(Exception):
                await client.create_webhook(url="https://example.com/hook", team_id=None, secret="secret")


# ---------------------------------------------------------------------------
# delete_webhook
# ---------------------------------------------------------------------------
class TestDeleteWebhook:

    @pytest.mark.asyncio
    async def test_delete_webhook_returns_none(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=MOCK_DELETE_WEBHOOK_RESPONSE):
            result = await client.delete_webhook(webhook_id="webhook-uuid-1")

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_webhook_calls_mutation(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=MOCK_DELETE_WEBHOOK_RESPONSE) as mock_post:
            await client.delete_webhook(webhook_id="webhook-uuid-1")

        mock_post.assert_called_once()
        query = mock_post.call_args[0][0]
        assert "webhookDelete" in query
        assert "mutation" in query.lower()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------
class TestLinearClientErrors:

    @pytest.mark.asyncio
    async def test_graphql_errors_raise_exception(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        error_response = {
            "errors": [
                {"message": "Authentication required"}
            ]
        }

        with patch.object(client, "_post", new_callable=AsyncMock, return_value=error_response):
            with pytest.raises(Exception):
                await client.get_organization()

    @pytest.mark.asyncio
    async def test_http_error_propagates(self):
        from src.services.linear_client import LinearClient
        client = LinearClient(access_token=ACCESS_TOKEN)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_async_client = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_async_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_async_client.post.side_effect = httpx.ConnectError("Connection refused")

            with pytest.raises(Exception):
                await client.get_organization()
