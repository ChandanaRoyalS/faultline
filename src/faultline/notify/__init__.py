"""Incident lifecycle notifications (T5.2).

*"Webhook notifications on incident open and report ready, with links into the UI."*

Four modules, split so that only one of them opens a socket:

- `messages` - what a notification says. Pure text, and the module with the security argument:
  **no caller-supplied value reaches a channel unescaped and unquoted.**
- `announce` - the `Notifier` seam and the rule that a notification never fails an incident.
- `slack` - the incoming webhook. The only place HTTP appears, and where the webhook URL is
  treated as the credential it is.
- `settings` - `FAULTLINE_NOTIFY_*`.
"""

from faultline.notify.announce import SILENT, Announcer, Delivery, Notifier, Recorded, Silent

__all__ = ["SILENT", "Announcer", "Delivery", "Notifier", "Recorded", "Silent"]
