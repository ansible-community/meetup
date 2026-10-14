# Contribute to Meetup documentation

The Ansible Community Meetup documentation is maintained in the open in [ansible-community/meetup](https://github.com/ansible-community/meetup). Small corrections and larger improvements are welcome.

## Make a documentation change

1. Open an issue or discussion if the change needs coordination, especially when it changes Meetup policy or shared service behavior.
2. Edit the relevant Markdown page. Prefer improving the existing guide over adding a second page that covers the same task.
3. Preview locally from the repository root:

   ```console
   uv sync --group docs
   uv run mkdocs serve
   ```

4. Check the page navigation and links, then submit a pull request explaining the reader task the change improves.

A documentation-only contribution does not require changes to the Python tooling. Follow the project's CI results before merging.

## Keep specifications aligned

Changes to operational tooling should update [the tooling specification](../reference/tooling-specification.md) and any affected Community Team task guide. Changes to Pretix authentication behavior should update [the authentication specification](../reference/pretix-discourse-auth-specification.md) and be coordinated with the standalone plugin repository. These specifications live here so contributors can review the documented contract alongside the guides.

All contributors follow the [Ansible Community Code of Conduct](https://docs.ansible.com/projects/ansible/devel/community/code_of_conduct.html).
