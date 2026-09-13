"""Resolve an automatic-modal/inbox race without retrying a native click.

This helper only opens the inbox. It must never wrap approval or denial clicks.
An intercepted click is accepted only when a read proves that the intended
modal is already open; every other WebDriver error remains a hard failure.
"""
from collections.abc import Callable


def open_pending_dialog(is_open: Callable[[], bool], click_inbox: Callable[[], None]) -> str:
    if is_open():
        return 'automatic'
    try:
        click_inbox()
    except RuntimeError as error:
        message = str(error)
        intercepted = any(text in message for text in ('element not interactable', 'element click intercepted'))
        if not intercepted or not is_open():
            raise
        return 'automatic-during-inbox-click'
    return 'native-inbox-click'
