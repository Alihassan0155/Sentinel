# Sentinel

## Personal memory

Sentinel stores semantic memories in PostgreSQL with pgVector. Start the database with
`docker compose up -d`, then start the API as usual; startup creates the `vector`
extension and `memories` table. Embeddings use `gemini-embedding-001` at 768
dimensions (override with `EMBEDDING_MODEL` only if it supports that dimension).

Updating `PUT /profile` refreshes the profile memory. New monitored findings are
remembered with their source URL. `POST /memory` records a preference, interaction,
decision, or outcome. `POST /memory/changes/{change_id}/feedback` records an
`interested`, `saved`, `applied`, `dismissed`, or `irrelevant` decision. The same
finding's feedback is updated on repeat calls. `GET /memory/search?q=...` retrieves
similar memories; `GET /memory` lists recent entries.

Relevance uses close prior decisions as a small score adjustment, and the
investigation prompt receives retrieved memories as personal context. Investigation
facts still require quotes from fetched source pages. Memory embedding happens only
when profile data or findings change, when feedback is recorded, and for new
findings that need retrieval.

## Recommendations

After a new finding is assessed and any investigation completes, Sentinel saves a
recommendation with a decision (`recommended`, `review`, or `skip`), reasons, priority,
and the relevance score used. The decision combines profile matches, prior user
feedback, and verified investigation details. A verified salary below the user's
minimum or an incompatible location causes a skip. Failed investigations lead to
review instead of an immediate recommendation. `GET /changes` returns each saved
decision; older findings receive a computed decision until they are reprocessed.
