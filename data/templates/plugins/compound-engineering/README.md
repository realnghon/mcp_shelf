# Compound Engineering Plugin Template

This directory is a repository-local template for mounting skills/plugins into MCP Shelf.

## Structure

- `skills/<skill-slug>/SKILL.md`
- `plugin.manifest.json` (optional metadata for your own lifecycle)

## How To Add A New Skill

1. Copy `skills/ce-brainstorm` to `skills/<your-skill-slug>`.
2. Edit `SKILL.md`.
3. Create a capability in MCP Shelf with:
   - `kind = "skill"`
   - `connection_config.path = "data/templates/plugins/compound-engineering/skills/<your-skill-slug>/SKILL.md"`
4. Mount that capability in a binding.

The runtime will expose it as a callable tool named `skill_<slug>` by default.
