# Database migrations

Executable Alembic scripts live in `src/sys_eden/migrations/` so the installed
application can initialize a fresh database without depending on a checkout.
`Database.initialize()` supplies the connection and backs up a database before
applying the baseline. Unknown schema revisions are rejected without downgrading.
Future schema changes require migrations and backup/recovery tests.
