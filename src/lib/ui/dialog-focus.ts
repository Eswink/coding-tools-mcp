/** Keep keyboard navigation inside an open local dialog, without invoking actions.
 * Native dialog inertness and Escape handling remain owned by the component.
 */
export function containDialogFocus(event: KeyboardEvent): void {
  if (event.key !== "Tab" || event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
  const dialog = event.currentTarget as HTMLDialogElement | null;
  if (!dialog?.open || dialog.tagName !== "DIALOG") return;
  const view = dialog.ownerDocument.defaultView;
  if (!view) return;
  // Re-evaluate on every key: pending operations can disable a complete fieldset.
  const controls = Array.from(dialog.querySelectorAll<HTMLElement>(
    'button, input, select, textarea, a[href], [tabindex]',
  )).filter(element => element.tabIndex >= 0 && !element.matches(':disabled, [hidden]')
    && !element.closest('[inert]') && element.getClientRects().length > 0
    && view.getComputedStyle(element).visibility !== 'hidden');
  if (controls.length === 0) {
    event.preventDefault();
    dialog.focus();
    return;
  }
  const current = controls.indexOf(dialog.ownerDocument.activeElement as HTMLElement);
  const boundary = event.shiftKey ? current <= 0 : current < 0 || current === controls.length - 1;
  if (boundary) {
    event.preventDefault();
    controls[event.shiftKey ? controls.length - 1 : 0].focus();
  }
}
