package main

import (
	"net"
	"strconv"
	"testing"
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
