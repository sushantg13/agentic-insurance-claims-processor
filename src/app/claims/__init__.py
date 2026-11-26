"""Claim intake and assessment code shared by the Lambda handlers.

Nothing in this package knows how it was triggered: handlers translate the
trigger's event into plain calls, so the same code serves an S3 drop today and
an API call from the UI later.
"""
