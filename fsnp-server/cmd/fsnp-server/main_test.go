package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"reflect"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestListenNetwork(t *testing.T) {
	cases := map[string]string{
		"0.0.0.0":   "tcp4", // the default: must be IPv4, see listenNetwork
		"127.0.0.1": "tcp",
		"10.0.0.5":  "tcp",
		"::":        "tcp6",
		"::1":       "tcp6",
		"localhost": "tcp",
		"":          "tcp",
	}
	for host, want := range cases {
		if got := listenNetwork(host); got != want {
			t.Errorf("listenNetwork(%q) = %q, want %q", host, got, want)
		}
	}
}

// TestDefaultListenConflicts is the regression test for the bug this
// replaced: with network "tcp", a second listener on a port an IPv4 socket
// already holds would succeed (Go binds dual-stack IPv6, which macOS/BSD
// allow alongside an IPv4 bind) and then receive no IPv4 connections.
func TestDefaultListenConflicts(t *testing.T) {
	const host = "0.0.0.0"
	first, err := net.Listen(listenNetwork(host), net.JoinHostPort(host, "0"))
	if err != nil {
		t.Fatal(err)
	}
	defer first.Close()
	port := first.Addr().(*net.TCPAddr).Port

	second, err := net.Listen(listenNetwork(host), net.JoinHostPort(host, strconv.Itoa(port)))
	if err == nil {
		second.Close()
		t.Fatalf("second listen on port %d succeeded, want an in-use error", port)
	}
}

func TestSplitList(t *testing.T) {
	cases := map[string][]string{
		"":                          nil,
		"203.0.113.4":               {"203.0.113.4"},
		"a.example, b.example":      {"a.example", "b.example"},
		" a.example ,, ,b.example,": {"a.example", "b.example"},
	}
	for in, want := range cases {
		if got := splitList(in); !reflect.DeepEqual(got, want) {
			t.Errorf("splitList(%q) = %q, want %q", in, got, want)
		}
	}
}

type readiness struct {
	Event string `json:"event"`
	Port  int    `json:"port"`
	Mode  string `json:"mode"`
}

// start runs the server in a goroutine on a free loopback port and returns
// its readiness line, a stop function, and a channel carrying the exit code.
func start(t *testing.T, stdin io.Reader, args ...string) (readiness, context.CancelFunc, <-chan int) {
	t.Helper()
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	r, w := io.Pipe()
	code := make(chan int, 1)
	args = append([]string{"--host=127.0.0.1", "--port=0", "--log-input=false"}, args...)
	go func() { code <- run(ctx, args, stdin, w) }()

	line := make(chan string, 1)
	go func() {
		s, _ := bufio.NewReader(r).ReadString('\n')
		line <- s
	}()
	var ready readiness
	select {
	case s := <-line:
		if err := json.Unmarshal([]byte(s), &ready); err != nil {
			t.Fatalf("readiness line %q: %v", s, err)
		}
	case c := <-code:
		t.Fatalf("exited with %d before the readiness line", c)
	case <-time.After(5 * time.Second):
		t.Fatal("no readiness line")
	}
	if ready.Event != "listening" || ready.Port == 0 {
		t.Fatalf("readiness %+v", ready)
	}
	return ready, cancel, code
}

func waitExit(t *testing.T, code <-chan int, want int) {
	t.Helper()
	select {
	case c := <-code:
		if c != want {
			t.Fatalf("exit code %d, want %d", c, want)
		}
	case <-time.After(10 * time.Second):
		t.Fatal("did not exit")
	}
}

func TestSingleGameMode(t *testing.T) {
	ready, cancel, code := start(t, strings.NewReader(""))
	if ready.Mode != "game" {
		t.Fatalf("mode %q, want game", ready.Mode)
	}
	cancel()
	waitExit(t, code, 0)
}

func TestLobbyMode(t *testing.T) {
	for _, tc := range []struct {
		name string
		env  string
		args []string
	}{
		{"flag", "", []string{"--lobby"}},
		{"env", "true", nil},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if tc.env != "" {
				t.Setenv("LOBBY", tc.env)
			}
			ready, cancel, code := start(t, strings.NewReader(""), tc.args...)
			if ready.Mode != "lobby" {
				t.Fatalf("mode %q, want lobby", ready.Mode)
			}
			base := fmt.Sprintf("http://127.0.0.1:%d", ready.Port)
			resp, err := http.Get(base + "/game/create?players=2&password=secret")
			if err != nil {
				t.Fatal(err)
			}
			body, _ := io.ReadAll(resp.Body)
			resp.Body.Close()
			v, err := url.ParseQuery(string(body))
			if resp.StatusCode != 200 || err != nil || v.Get("port") != strconv.Itoa(ready.Port) {
				t.Fatalf("create: %d %q", resp.StatusCode, body)
			}
			cancel()
			waitExit(t, code, 0)
		})
	}
}

// TestLobbyExitsOnStdinClose: the launcher's supervision contract holds in
// lobby mode too, should it ever run one.
func TestLobbyExitsOnStdinClose(t *testing.T) {
	r, w := io.Pipe()
	_, _, code := start(t, r, "--lobby", "--exit-on-stdin-close")
	_ = w.Close()
	waitExit(t, code, 0)
}

// TestListenFailureReported: a port already in use is reported on stdout as
// an error event the launcher can recognise, not just a non-zero exit.
func TestListenFailureReported(t *testing.T) {
	held, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer held.Close()
	port := held.Addr().(*net.TCPAddr).Port

	for _, mode := range [][]string{nil, {"--lobby"}} {
		var out strings.Builder
		args := append([]string{"--host=127.0.0.1", "--port=" + strconv.Itoa(port)}, mode...)
		if code := run(context.Background(), args, strings.NewReader(""), &out); code != 1 {
			t.Fatalf("%v: exit code %d, want 1", mode, code)
		}
		var ev struct {
			Event, Reason, Message string
			Port                   int
		}
		if err := json.Unmarshal([]byte(out.String()), &ev); err != nil {
			t.Fatalf("%v: stdout %q: %v", mode, out.String(), err)
		}
		if ev.Event != "error" || ev.Reason != "address_in_use" || ev.Port != port || ev.Message == "" {
			t.Fatalf("%v: got %+v", mode, ev)
		}
	}
}
