# Provision the event environment

Use this procedure when installing or reconciling the shared Forum and Pretix setup. Access to API credentials and production systems must be limited to authorized Community Team maintainers.

## Prerequisites

- Access to the canonical `ansible-community/meetup` repository and its `uv` environment.
- Authorized Pretix and Forum API credentials configured as described in the [tooling specification](../reference/tooling-specification.md).
- A reviewed change for any city registry or environment configuration update.

## Procedure

1. Update the checkout and install locked dependencies with `uv sync`.
2. Confirm the target Pretix URL and Forum API credentials point to the intended environment. Production RSVP is [rsvp.ansible.com](https://rsvp.ansible.com); tooling defaults to localhost for development.
3. Run the environment provisioner from the repository root:

   ```console
   uv run python -m tools.environment.provision_environment
   ```
4. Review output and verify the Forum groups/categories and Pretix teams/template before creating events.
5. Record and resolve any reported API errors; do not announce an event until the environment is reconciled.

Provisioning reconciles named groups and permissions. Review the specification before changing access behavior.
