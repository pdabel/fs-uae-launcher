package game

import (
	"testing"
	"time"
)

// TestRealClockTickerKeepsSchedule checks the real ticker fires on the
// start+n*d schedule rather than d after each receive: consuming ticks
// slowly must not stretch the overall cadence.
func TestRealClockTickerKeepsSchedule(t *testing.T) {
	const d = 5 * time.Millisecond
	const n = 40
	tk := RealClock{}.NewTicker(d)
	defer tk.Stop()
	start := time.Now()
	for i := 0; i < n; i++ {
		select {
		case <-tk.C():
		case <-time.After(time.Second):
			t.Fatalf("tick %d never arrived", i)
		}
		if i%10 == 0 {
			// A late receiver: the next ticks should come back to back,
			// not one full period after this delay.
			time.Sleep(3 * d)
		}
	}
	elapsed := time.Since(start)
	// 40 ticks at 5 ms is 200 ms on schedule. The four 15 ms sleeps must
	// not add to that: the ticks that fell due during a sleep are
	// delivered back to back afterwards. A receive-relative ticker would
	// take 260 ms; one that drops ticks would take 240 ms.
	if elapsed < n*d || elapsed > n*d+4*d {
		t.Fatalf("40 ticks took %v, want about %v", elapsed, n*d)
	}
}

func TestRealClockTickerStop(t *testing.T) {
	tk := RealClock{}.NewTicker(time.Millisecond)
	<-tk.C()
	tk.Stop()
	tk.Stop() // idempotent
	select {
	case <-tk.C():
		t.Fatal("tick after Stop")
	case <-time.After(10 * time.Millisecond):
	}
}
