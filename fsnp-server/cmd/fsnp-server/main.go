// Command fsnp-server hosts one FSNP v1 netplay game, as
// launcher/server/game.py did. It takes the same --port/--players/--password/
// --launch-timeout flags so launcher/server/Server.py can spawn it in place
// of the Python script, prints a one-line JSON readiness event on stdout once
// it is listening, and exits on its own when the game ends or on SIGTERM.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"net"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/fsnp"
	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/game"
)

func main() {
	os.Exit(run())
}

func run() int {
	var (
		host          = flag.String("host", envOr("HOST", "0.0.0.0"), "address to listen on")
		port          = flag.Int("port", envInt("PORT", 25101), "port to listen on (0 picks a free one; see the readiness line)")
		players       = flag.Int("players", envInt("PLAYERS", 2), "number of players the game waits for")
		password      = flag.String("password", envOr("PASSWORD", ""), "game password")
		launchTimeout = flag.Int("launch-timeout", envInt("LAUNCH_TIMEOUT", 0), "seconds to wait from startup for all players to join; 0 = forever")
		exitOnStdin   = flag.Bool("exit-on-stdin-close", false, "stop the game and exit when stdin reaches EOF (for a supervising launcher)")
		verbose       = flag.Bool("verbose", false, "debug logging")
	)
	flag.Parse()

	level := slog.LevelInfo
	if *verbose {
		level = slog.LevelDebug
	}
	log := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: level}))

	g, err := game.New(game.Config{
		Players:       *players,
		PasswordHash:  fsnp.PasswordHash(*password),
		LaunchTimeout: time.Duration(*launchTimeout) * time.Second,
		Logger:        log,
	})
	if err != nil {
		log.Error("invalid configuration", "err", err)
		return 1
	}

	ln, err := net.Listen("tcp", net.JoinHostPort(*host, strconv.Itoa(*port)))
	if err != nil {
		log.Error("listen failed", "err", err)
		return 1
	}
	actualPort := ln.Addr().(*net.TCPAddr).Port
	log.Info("listening", "host", *host, "port", actualPort, "players", *players)

	// Readiness line: the launcher reads stdout until it sees this.
	ready, _ := json.Marshal(map[string]any{"event": "listening", "port": actualPort})
	fmt.Fprintln(os.Stdout, string(ready))

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigs := make(chan os.Signal, 1)
	signal.Notify(sigs, os.Interrupt, syscall.SIGTERM)
	go func() {
		s := <-sigs
		log.Info("signal received, stopping", "signal", s)
		cancel()
	}()
	if *exitOnStdin {
		go func() {
			_, _ = io.Copy(io.Discard, os.Stdin)
			log.Info("stdin closed, stopping")
			cancel()
		}()
	}

	go func() {
		if err := g.Serve(ctx, ln); err != nil {
			log.Error("accept loop failed", "err", err)
			cancel()
		}
	}()

	err = g.Run(ctx)
	switch {
	case err == nil:
		log.Info("game ended")
		return 0
	case errors.Is(err, game.ErrLaunchTimeout):
		log.Warn("game never started", "err", err)
		return 2
	case errors.Is(err, game.ErrDesync):
		log.Warn("game ended with a desync", "err", err)
		return 3
	default:
		log.Error("game failed", "err", err)
		return 1
	}
}

func envOr(key, def string) string {
	if v, ok := os.LookupEnv(key); ok {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	if v, ok := os.LookupEnv(key); ok {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}
