# Full-package compatibility wrapper.
# We intentionally keep the legacy full build spec unchanged and expose a new
# explicit entrypoint so release automation can choose between full/lite builds.
exec(open("SuperPicky.spec", "r", encoding="utf-8").read())

