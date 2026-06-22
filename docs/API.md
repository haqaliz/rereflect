# API Reference

Rereflect exposes a REST API under `/api/v1`. When the backend is running, the full
interactive OpenAPI/Swagger docs are at **http://localhost:8000/docs** — this page is a
quick map of the most common endpoints.

## Authentication

All protected endpoints require a JWT bearer token:

```
Authorization: Bearer <token>
```

```
POST /api/v1/auth/signup
POST /api/v1/auth/login
GET  /api/v1/auth/me
```

## Multi-tenancy

All data is scoped by `organization_id`, which is extracted from the JWT. You only ever
see and act on your own organization's data.

## Feedback

```
GET    /api/v1/feedback              # List (paginated, filterable)
POST   /api/v1/feedback              # Create
GET    /api/v1/feedback/{id}         # Get one
PUT    /api/v1/feedback/{id}         # Update
DELETE /api/v1/feedback/{id}         # Delete
POST   /api/v1/feedback/import       # CSV import
```

### Pagination

```
GET /api/v1/feedback?page=1&page_size=20&sort_by=created_at&sort_order=desc
```

`page_size` must not exceed 100.

### Filtering

```
GET /api/v1/feedback?sentiment=negative&is_urgent=true&search=payment
```

## Dashboard

```
GET /api/v1/dashboard                # Aggregated analytics data
```

## Team management

```
GET    /api/v1/team                  # List members
POST   /api/v1/team/invite           # Send invite
PATCH  /api/v1/team/{id}/role        # Change role
DELETE /api/v1/team/{id}             # Remove member
```

## Common gotchas

- **Trailing slashes** — match the route exactly; a missing/extra `/` can return 422.
- **`page_size`** — keep it ≤ 100.
- **422 validation errors** — ensure all required fields are present and typed correctly.
