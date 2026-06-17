"""Pure scheduling core.

Nothing in this package may import ``gspread`` or touch the filesystem. It
takes plain domain objects in and returns a ``Proposal`` out, so the logic
stays portable and unit-testable without auth or network.
"""
