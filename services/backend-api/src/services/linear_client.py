"""
Linear GraphQL API client.

Wraps Linear's GraphQL API using httpx.AsyncClient.
All mutations require an OAuth access token from the connected org.
"""
import httpx
from typing import Optional


class LinearClient:
    """Linear GraphQL API client."""

    GRAPHQL_URL = "https://api.linear.app/graphql"

    def __init__(self, access_token: str):
        self.access_token = access_token

    async def _post(self, query: str, variables: Optional[dict] = None) -> dict:
        """Execute a GraphQL query/mutation against the Linear API."""
        payload: dict = {"query": query}
        if variables:
            payload["variables"] = variables

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.GRAPHQL_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

        if "errors" in data:
            messages = "; ".join(e.get("message", "Unknown error") for e in data["errors"])
            raise Exception(f"Linear GraphQL error: {messages}")

        return data

    async def get_organization(self) -> dict:
        """Fetch the connected Linear organization."""
        query = """
        query {
          organization {
            id
            name
            urlKey
          }
        }
        """
        result = await self._post(query)
        return result["data"]["organization"]

    async def get_teams(self) -> list[dict]:
        """Fetch all teams in the Linear organization."""
        query = """
        query {
          teams {
            nodes {
              id
              name
              key
            }
          }
        }
        """
        result = await self._post(query)
        return result["data"]["teams"]["nodes"]

    async def get_projects(self, team_id: str) -> list[dict]:
        """Fetch projects for a given Linear team."""
        query = """
        query GetTeamProjects($teamId: String!) {
          team(id: $teamId) {
            projects {
              nodes {
                id
                name
              }
            }
          }
        }
        """
        result = await self._post(query, variables={"teamId": team_id})
        return result["data"]["team"]["projects"]["nodes"]

    async def get_labels(self) -> list[dict]:
        """Fetch all issue labels in the Linear organization."""
        query = """
        query {
          issueLabels {
            nodes {
              id
              name
              color
            }
          }
        }
        """
        result = await self._post(query)
        return result["data"]["issueLabels"]["nodes"]

    async def get_workflow_states(self, team_id: str) -> list[dict]:
        """Fetch workflow states for a given Linear team."""
        query = """
        query GetWorkflowStates($teamId: String!) {
          workflowStates(filter: { team: { id: { eq: $teamId } } }) {
            nodes {
              id
              name
              type
            }
          }
        }
        """
        result = await self._post(query, variables={"teamId": team_id})
        return result["data"]["workflowStates"]["nodes"]

    async def create_issue(self, input: dict) -> dict:
        """Create a Linear issue. Raises if creation fails."""
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
          issueCreate(input: $input) {
            success
            issue {
              id
              identifier
              url
              title
              state {
                name
                type
              }
              priority
              assignee {
                name
              }
            }
          }
        }
        """
        result = await self._post(mutation, variables={"input": input})
        payload = result["data"]["issueCreate"]
        if not payload["success"]:
            raise Exception("Linear issue creation failed: success=false")
        return payload["issue"]

    async def create_webhook(self, url: str, team_id: Optional[str], secret: str) -> dict:
        """Register a Linear webhook. Raises if creation fails."""
        mutation = """
        mutation CreateWebhook($input: WebhookCreateInput!) {
          webhookCreate(input: $input) {
            success
            webhook {
              id
              url
              secret
              enabled
            }
          }
        }
        """
        webhook_input: dict = {
            "url": url,
            "secret": secret,
            "resourceTypes": ["Issue"],
        }
        if team_id:
            webhook_input["teamId"] = team_id

        result = await self._post(mutation, variables={"input": webhook_input})
        payload = result["data"]["webhookCreate"]
        if not payload["success"]:
            raise Exception("Linear webhook creation failed: success=false")
        return payload["webhook"]

    async def delete_webhook(self, webhook_id: str) -> None:
        """Delete a Linear webhook by ID."""
        mutation = """
        mutation DeleteWebhook($id: String!) {
          webhookDelete(id: $id) {
            success
          }
        }
        """
        result = await self._post(mutation, variables={"id": webhook_id})
        payload = result["data"]["webhookDelete"]
        if not payload["success"]:
            raise Exception(f"Linear webhook deletion failed for id={webhook_id}")
        return None
