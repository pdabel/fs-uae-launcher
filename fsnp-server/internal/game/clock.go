package game

import (
	"sync"
	"time"
)

// Clock is the source of time for a Game. The real implementation wraps the
// time package; tests substitute one they drive by hand so the 20 ms tick,
// ping RTTs and the launch timeout are deterministic.
type Clock interface {
	Now() time.Time
	NewTicker(d time.Duration) Ticker
	After(d time.Duration) <-chan time.Time
}

// Ticker delivers ticks on C until Stop is called.
type Ticker interface {
	C() <-chan time.Time
	Stop()
}

// RealClock is the Clock backed by the time package.
type RealClock struct{}

func (RealClock) Now() time.Time { return time.Now() }

// NewTicker returns a ticker that fires at start+n*d and catches up rather
// than skipping: if a wakeup is late by more than one period, the missed
// ticks are delivered back to back, the same way game.py's
// `self.time = target_time` accumulated. time.Ticker is deliberately not used
// here — it drops missed periods, which showed up in a real session as
// ~11 skipped frames over 7.6 minutes on loopback (each a 20 ms hitch in
// every emulator). Ticks are never dropped: the send blocks until the game
// goroutine takes it, so however late the wakeup, every frame is delivered.
func (RealClock) NewTicker(d time.Duration) Ticker {
	t := &deadlineTicker{c: make(chan time.Time), stop: make(chan struct{})}
	go t.run(d)
	return t
}

func (RealClock) After(d time.Duration) <-chan time.Time { return time.After(d) }

type deadlineTicker struct {
	c    chan time.Time
	stop chan struct{}
	once sync.Once
}

func (t *deadlineTicker) C() <-chan time.Time { return t.c }
func (t *deadlineTicker) Stop()               { t.once.Do(func() { close(t.stop) }) }

func (t *deadlineTicker) run(d time.Duration) {
	next := time.Now().Add(d)
	for {
		timer := time.NewTimer(time.Until(next))
		select {
		case <-t.stop:
			timer.Stop()
			return
		case now := <-timer.C:
			select {
			case t.c <- now:
			case <-t.stop:
				return
			}
			next = next.Add(d)
		}
	}
}
