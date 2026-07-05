# Decisions
[qwen][2026-07-01T14:30] placed memory instances under .qwen\agent-memory\ rather than project root — keeps them private to Qwen, separate from user projects.
[qwen][2026-07-01T14:30] created a shared PROTOCOL.md at agent-memory\ root — both instances follow the same protocol; agents read it before first use.
