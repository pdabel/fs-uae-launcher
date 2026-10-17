// Command fsnp-server hosts FSNP v1 netplay games.
//
// By default it hosts one game, as launcher/server/game.py did. It takes the
// same --port/--players/--password/--launch-timeout flags so
// launcher/server/Server.py can spawn it in place of the Python script, and
// exits on its own when the game ends or on SIGTERM.
//
// With --lobby it instead hosts many games on the one port: an HTTP API
// (GET /game/create, what /startgame calls) and every game it creates share
// the listener, and connections find their game by password hash. It runs
// until SIGTERM. See internal/lobby.
//
// Either way it prints a one-line JSON readiness event on stdout once it is
// listening.
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
	"strings"
	"syscall"
	"time"

	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/fsnp"
	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/game"
	"github.com/pdabel/fs-uae-launcher/fsnp-server/internal/lobby"
)

func main() {
	os.Exit(run(context.Background(), os.Args[1:], os.Stdin, os.Stdout))
}

// run is main with its inputs passed in, so tests can drive it: cancelling
// ctx stops it as SIGTERM does. It returns the process exit code.
func run(ctx context.Context, args []string, stdin io.Reader, stdout io.Writer) int {
	fs := flag.NewFlagSet("fsnp-server", flag.ContinueOnError)
	var (
		host          = fs.String("host", envOr("HOST", "0.0.0.0"), "address to listen on")
		port          = fs.Int("port", envInt("PORT", 25101), "port to listen on (0 picks a free one; see the readiness line)")
		players       = fs.Int("players", envInt("PLAYERS", 2), "number of players the game waits for (single game only)")
		password      = fs.String("password", envOr("PASSWORD", ""), "game password (single game only)")
		launchTimeout = fs.Int("launch-timeout", envInt("LAUNCH_TIMEOUT", 0), "seconds to wait from startup for all players to join; 0 = forever (single game only)")
		exitOnStdin   = fs.Bool("exit-on-stdin-close", false, "stop and exit when stdin reaches EOF (for a supervising launcher)")
		logFile       = fs.String("log-file", envOr("LOG_FILE", ""), "also append the log to this file")
		logInput      = fs.Bool("log-input", true, "log every relayed input event (sender, action, state, recipients)")
		verbose       = fs.Bool("verbose", false, "debug logging")

		lobbyMode       = fs.Bool("lobby", envBool("LOBBY", false), "host many games on --port, created over HTTP with GET /game/create")
		maxGames        = fs.Int("max-games", envInt("MAX_GAMES", lobby.DefaultMaxGames), "lobby: most games live at once")
		gameTimeout     = fs.Int("game-launch-timeout", envInt("GAME_LAUNCH_TIMEOUT", int(lobby.DefaultLaunchTimeout/time.Second)), "lobby: seconds a game may wait for its players before it is reaped")
		publicAddresses = fs.String("public-addresses", envOr("PUBLIC_ADDRESSES", ""), "lobby: comma-separated addresses to tell players; empty = the host name the creator used")
	)
	if err := fs.Parse(args); err != nil {
		return 2
	}

	level := slog.LevelInfo
	if *verbose {
		level = slog.LevelDebug
	}
	// Logs go to stderr so the launcher's inherited stderr picks them up and
	// stdout carries only the readiness line. --log-file adds a copy on disk,
	// which is what to reach for when a session needs to be reported on
	// afterwards rather than watched live.
	var out io.Writer = os.Stderr
	if *logFile != "" {
		f, err := os.OpenFile(*logFile, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
		if err != nil {
			fmt.Fprintf(os.Stderr, "could not open log file: %v\n", err)
			return 1
		}
		defer f.Close()
		out = io.MultiWriter(os.Stderr, f)
	}
	log := slog.New(slog.NewTextHandler(out, &slog.HandlerOptions{Level: level}))

	var g *game.Game
	var l *lobby.Lobby
	if *lobbyMode {
		fs.Visit(func(f *flag.Flag) {
			switch f.Name {
			case "players", "password", "launch-timeout":
				log.Warn("flag ignored in lobby mode; each game sets its own", "flag", f.Name)
			}
		})
		l = lobby.New(lobby.Config{
			MaxGames:        *maxGames,
			LaunchTimeout:   time.Duration(*gameTimeout) * time.Second,
			PublicAddresses: splitList(*publicAddresses),
			Logger:          log,
			LogInput:        *logInput,
		})
	} else {
		var err error
		g, err = game.New(game.Config{
			Players:       *players,
			PasswordHash:  fsnp.ExpectedPasswordHash(*password),
			LaunchTimeout: time.Duration(*launchTimeout) * time.Second,
			Logger:        log,
			LogInput:      *logInput,
		})
		if err != nil {
			log.Error("invalid configuration", "err", err)
			return 1
		}
	}

	ln, err := net.Listen(listenNetwork(*host), net.JoinHostPort(*host, strconv.Itoa(*port)))
	if err != nil {
		log.Error("listen failed", "err", err)
		return 1
	}
	actualPort := ln.Addr().(*net.TCPAddr).Port
	mode := "game"
	if *lobbyMode {
		mode = "lobby"
		log.Info("listening", "mode", mode, "host", *host, "port", actualPort,
			"network", listenNetwork(*host), "max_games", *maxGames,
			"game_launch_timeout", time.Duration(*gameTimeout)*time.Second,
			"public_addresses", *publicAddresses, "log_input", *logInput)
	} else {
		log.Info("listening", "mode", mode, "host", *host, "port", actualPort, "players", *players,
			"network", listenNetwork(*host), "log_input", *logInput,
			"password_set", *password != "")
	}
	if *logFile != "" {
		log.Info("logging to file", "path", *logFile)
	}

	// Readiness line: the launcher reads stdout until it sees this.
	ready, _ := json.Marshal(map[string]any{"event": "listening", "port": actualPort, "mode": mode})
	fmt.Fprintln(stdout, string(ready))

	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	sigs := make(chan os.Signal, 1)
	signal.Notify(sigs, os.Interrupt, syscall.SIGTERM)
	defer signal.Stop(sigs)
	go func() {
		select {
		case s := <-sigs:
			log.Info("signal received, stopping", "signal", s)
			cancel()
		case <-ctx.Done():
		}
	}()
	if *exitOnStdin {
		go func() {
			_, _ = io.Copy(io.Discard, stdin)
			log.Info("stdin closed, stopping")
			cancel()
		}()
	}

	if l != nil {
		if err := l.Serve(ctx, ln); err != nil {
			log.Error("accept loop failed", "err", err)
			return 1
		}
		log.Info("lobby stopped")
		return 0
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

// listenNetwork picks the network for net.Listen based on the host.
//
// For the IPv4 wildcard — the default, and what game.py's socket.socket()
// always used — this must be "tcp4" rather than "tcp". Go resolves
// "0.0.0.0:port" to a *dual-stack IPv6* socket, and on macOS/BSD binding
// [::]:port does not conflict with an existing IPv4 listener on the same
// port: both binds succeed, incoming IPv4 connections go to the IPv4
// socket, and this server would report itself listening while receiving
// nothing. Asking for "tcp4" makes a port conflict the bind error it should
// be, so the launcher finds out at spawn time instead of announcing a game
// nobody can reach.
func listenNetwork(host string) string {
	if host == "0.0.0.0" {
		return "tcp4"
	}
	if ip := net.ParseIP(host); ip != nil && ip.To4() == nil {
		return "tcp6"
	}
	return "tcp"
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

func envBool(key string, def bool) bool {
	if v, ok := os.LookupEnv(key); ok {
		if b, err := strconv.ParseBool(v); err == nil {
			return b
		}
	}
	return def
}

// splitList splits a comma-separated flag value, dropping blanks.
func splitList(s string) []string {
	var out []string
	for _, part := range strings.Split(s, ",") {
		if part = strings.TrimSpace(part); part != "" {
			out = append(out, part)
		}
	}
	return out
}
