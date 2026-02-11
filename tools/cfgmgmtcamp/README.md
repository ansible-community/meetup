# CfgMgmtCamp Notes Generator

A tool to help generate hackmd in advance to capture discussions.

When run after the event with `--check-for-slides` identifies which talks haven't uploaded slides.

## Quick Start

Three commands in chronological order for managing your track:

```bash
# 1. Review all talks and identify ones to promote, looks for any talks that contain the term "ansible" in title, abstract, notes, etc
python3 create-cfgmgmtcamp-notes.py --year 2026 --track ansible --list-talks

# 2. Create Markdown file for all talks that are part of the Ansible track
python3 create-cfgmgmtcamp-notes.py --year 2026 --track ansible --generate-notes

# 3. After event, identify which presenters need to upload slides
python3 create-cfgmgmtcamp-notes.py --year 2026 --track ansible --check-for-slides
```

## Example output

### ./create-cfgmgmtcamp-notes.py --year 2026 --generate-notes
```
CfgMgmtCamp 2026
Track: Ansible
Downloading schedule for ghent2026...

Extracting talks...
Found 19 talks

Extracting related talks...
Found 12 related talks from other tracks
```

**cfgmgmtcamp2026_ansible_notes.md**

```
###### tags: `CfgMgmtCamp 2026`

# Ansible talks CfgMgmtCamp 2026

- Short link to this HackMD: <https://red.ht/ghent2026> (ENSURE this is created)
- [Contributor Summit agenda in the forum](https://forum.ansible.com/FIXME) (ENSURE this is created)
- [Ansible Code of Conduct](https://docs.ansible.com/projects/ansible/latest/community/code_of_conduct.html)
- Live stream:
    - Monday: Room [B.1.0.14](https://www.youtube.com/watch?v=FIXME) UPDATE THIS
    - Monday: Room [B.1.017](https://www.youtube.com/watch?v=FIXME) UPDATE THIS
    - Monday: Room [B.2.015](https://www.youtube.com/watch?v=FIXME) UPDATE THIS
    - Tuesday: Room [B.1.0.14](https://www.youtube.com/watch?v=FIXME) UPDATE THIS
    - Tuesday: Room [B.1.017](https://www.youtube.com/watch?v=FIXME) UPDATE THIS
    - Wednesday:  [Contributors Summit](https://www.youtube.com/watch?v=FIXME) UPDATE THIS

## Overview

Everybody is welcome to make notes on the talks, especially any ideas, actions and offers to get involved.

# Monday

### Talk: Composing systems in an automated way with Ansible, Podman, and bootc

by Fabio Alessandro "Fale" Locati

* Slides: [Slides](https://cfp.cfgmgmtcamp.org/media/ghent2026/submissions/KU78JX/resources/handout_KIJdbfs.pdf)
* Video:

#### Abstract

As organizations increasingly adopt containerization, Kubernetes has become the de facto standard for orchestrating clusters. However, for many teams, the complexity and operational overhead of managing a Kubernetes environment can be daunting.
In this talk, we'll explore a practical alternative built on open standards and simple tools: using:
* Ansible for automation
* Podman for container management
* bootc for the operating system.
While Ansible and Podman are very established technologies, bootc is an emerging technology that reimagines how systems are built and updated by transforming container images into fully bootable, atomic operating systems. It brings the simplicity, consistency, and automation of container workflows all the way down to the OS layer.
You'll learn how to use Ansible to define and manage containerized applications and services, leverage Podman's daemonless architecture for secure deployments, and then go one step further by using bootc to build and manage image-based operating systems directly from your container definitions.
We'll wrap up with a live demo creating podman containers using Ansible on a bootc system, showing how these tools together can deliver lightweight, reproducible, and maintainable infrastructure in a simple way.

#### Talk summary

#### Ideas & followups

#### Questions
```


### ./create-cfgmgmtcamp-notes.py --year 2026 --track ansible--check-for-slides
```
Tuesday | 16:50
  Title: Writing, running, and testing awesome Ansible content with natural language and AI - powered by Ansible's MCP server
  Presenter: Shatakshi Mishra
  Resources:
    - ✅ [Slides](https://cfp.cfgmgmtcamp.org/media/ghent2026/submissions/WG9ST8/resources/Writing_running_and_testing_Ansible_content_with_MmucWqV.pptx)

Tuesday | 16:50
  Title: A Love Letter to Ansible Core 2.19
  Presenter: Matt Davis
  Resources: ❌ No resources

```

## Command Line Reference

### Required Arguments

- `--year YEAR`: Conference year (e.g., 2026)

### Track Selection

- `--track TRACK`: Track name to filter talks (default: ansible)
  - Examples: ansible, kubernetes, observability, foreman, puppet
  - Case-insensitive, converted to title case internally

### Mode Selection (choose one)

- `--generate-notes`: Generate HackMD-ready markdown file
- `--check-for-slides`: Check slide availability (terminal output only)
- `--list-talks`: List speaker names and talk titles (terminal output only)

## Output Files

| Mode | File Created | Size | Description |
|------|--------------|------|-------------|
| `--generate-notes` | `cfgmgmtcamp{year}_{track}_notes.md` | ~32KB | HackMD-ready notes file |
| `--check-for-slides` | None | - | Terminal output only |
| `--list-talks` | None | - | Terminal output only |

## Requirements

```bash
pip install jinja2
```
