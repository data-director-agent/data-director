"""The Data Director admin service: a read-only view of one deployment for its operators.

It listens on loopback only and has no sign-in: whoever can reach it has a shell on the VM, and
reaches it through an SSH tunnel (docs/guide/operations/admin.md). It reads the run and project
stores, the agents' cards, the deployment's settings and what `data-director doctor` reports, and
changes none of them. Every change is still made on the command line, and each page names the
command.
"""
