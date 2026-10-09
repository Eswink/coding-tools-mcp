package main

import "testing"

func TestGuestRunDiscardRequiresNoDirectoryAndNoCommandEffects(t *testing.T) {
	for _, c := range []struct {
		name               string
		directory, command bool
		mayDiscard         bool
	}{
		{"no_native_effect", false, false, true},
		{"created_directory_without_command", true, false, false},
		{"command_without_directory", false, true, false},
		{"directory_and_command", true, true, false},
	} {
		t.Run(c.name, func(t *testing.T) {
			if got := guestRunCanDiscard(c.directory, c.command); got != c.mayDiscard {
				t.Fatalf("effect owner discard=%v, want %v", got, c.mayDiscard)
			}
		})
	}
}
