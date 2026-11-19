"""The Data Director configuration tool, run by `scripts/dd.py`: `setup`, `start`, `doctor` and
`secret`, in development or on a VM.

One module per command, with what they share in `common` and the files development reads and
writes in `paths`. `vm` says where a VM keeps the deployment and reads it through `System`, which
tests replace; `vm_doctor` is `doctor` there.
"""
