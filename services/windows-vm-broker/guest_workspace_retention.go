package main

// Internal conservative discard policy only, never native authorization or an
// output seal. Effects are set by the registered owner BEFORE their native call.
// Checked file-handle close does not prove directory disposition. Once either
// effect was attempted, the whole owner stays held for actual VM/disposition.
func guestRunCanDiscard(createMayHaveEffect, commandMayHaveEffect bool) bool {
	return !createMayHaveEffect && !commandMayHaveEffect
}
