# Builds the FS-UAE netplay server. Run from this directory:
#
#   make           build ./fsnp-server for this machine
#   make check     gofmt, go vet and the test suite with -race
#   make help      list every target
#
# A local Go toolchain is used when there is one; otherwise the same commands
# run inside a golang container, so installing Go is optional. Set GO_DOCKER=1
# to force the container path even when Go is installed.
#
# The container builds for *this* machine's OS and architecture, not the
# container's: the image is Linux, so without GOOS/GOARCH a macOS or Windows
# developer would get a Linux binary that cannot run. CGO_ENABLED=0 makes that
# cross-compilation work with no toolchain beyond Go itself.

BINARY := fsnp-server
PKG := ./cmd/fsnp-server
# Explicit rather than ".": gofmt walks directories, and "." would include
# $(CACHE_DIR).
SRC_DIRS := cmd internal

# Kept in step with fsbuild/build.sh, which builds the binary for packaged
# releases. Change both together.
BUILD_FLAGS := -trimpath
LDFLAGS := -s -w

# Debian-based rather than the alpine image Dockerfile uses: it ships gcc, so
# `make test` can use -race, which needs cgo.
GO_VERSION ?= 1.24
GO_IMAGE ?= golang:$(GO_VERSION)

# Go's build and module caches, so repeat container builds are not cold.
CACHE_DIR := .gocache

# ---------------------------------------------------------------------------
# Toolchain selection
# ---------------------------------------------------------------------------

ifeq ($(GO_DOCKER),1)
LOCAL_GO :=
else
LOCAL_GO := $(shell command -v go 2>/dev/null)
endif

UNAME_S := $(shell uname -s)
UNAME_M := $(shell uname -m)

ifneq (,$(findstring MINGW,$(UNAME_S)))
HOST_GOOS := windows
else ifneq (,$(findstring MSYS,$(UNAME_S)))
HOST_GOOS := windows
else ifeq ($(UNAME_S),Darwin)
HOST_GOOS := darwin
else
HOST_GOOS := linux
endif

ifneq (,$(filter $(UNAME_M),x86_64 amd64))
HOST_GOARCH := amd64
else ifneq (,$(filter $(UNAME_M),arm64 aarch64))
HOST_GOARCH := arm64
else
HOST_GOARCH := $(UNAME_M)
endif

ifeq ($(HOST_GOOS),windows)
EXE := .exe
else
EXE :=
endif

# run_cmd takes a list of VAR=VALUE environment settings and a full command
# line (go build …, gofmt -l …), and runs it either locally or in the
# container.
ifeq ($(LOCAL_GO),)

DOCKER := $(shell command -v docker 2>/dev/null)
ifeq ($(DOCKER),)
$(error Neither go nor docker was found on PATH. Install one of them: Go, or \
Docker so this Makefile can build inside a $(GO_IMAGE) container)
endif

TOOLCHAIN := $(GO_IMAGE) container (no local go on PATH)
# --user keeps the binary and caches owned by the invoking user rather than
# root. HOME is pointed at the mounted cache because / is not writable for it.
run_cmd = docker run --rm \
	--user $(shell id -u):$(shell id -g) \
	--volume "$(CURDIR)":/src \
	--volume "$(CURDIR)/$(CACHE_DIR)":/cache \
	--workdir /src \
	--env HOME=/cache \
	--env GOCACHE=/cache/build \
	--env GOMODCACHE=/cache/mod \
	--env GOFLAGS=-buildvcs=false \
	$(addprefix --env ,$(1)) \
	$(GO_IMAGE) $(2)

else

TOOLCHAIN := $(shell go version)
run_cmd = env $(1) $(2)

endif

.PHONY: all build test vet fmt fmt-check check image clean help toolchain

all: build

# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

## build: compile ./fsnp-server for this machine (the default target)
build: $(CACHE_DIR)
	@echo "Building $(BINARY)$(EXE) for $(HOST_GOOS)/$(HOST_GOARCH) using $(TOOLCHAIN)"
	$(call run_cmd,CGO_ENABLED=0 GOOS=$(HOST_GOOS) GOARCH=$(HOST_GOARCH),\
		go build $(BUILD_FLAGS) -ldflags="$(LDFLAGS)" -o $(BINARY)$(EXE) $(PKG))
	@echo "Built $(CURDIR)/$(BINARY)$(EXE)"

## test: run the test suite with the race detector
# Not cross-compiled and not CGO_ENABLED=0: -race needs cgo, and a race
# detector build only runs on the platform it was built for. In the container
# that means the tests run as linux/$(HOST_GOARCH), which is what CI does too.
test: $(CACHE_DIR)
	$(call run_cmd,CGO_ENABLED=1,go test ./... -race -count=1)

## vet: run go vet
vet: $(CACHE_DIR)
	$(call run_cmd,,go vet ./...)

## fmt: rewrite sources with gofmt
fmt: $(CACHE_DIR)
	$(call run_cmd,,gofmt -w $(SRC_DIRS))

## fmt-check: fail if any source is not gofmt-clean
# gofmt, not `go fmt`: the latter only forwards -n/-x and always rewrites.
# `|| exit 1` matters — without it a failing gofmt yields empty output and
# this reports success.
fmt-check: $(CACHE_DIR)
	@unformatted=`$(call run_cmd,,gofmt -l $(SRC_DIRS))` || exit 1; \
	if [ -n "$$unformatted" ]; then \
		echo "Not gofmt-clean:"; echo "$$unformatted"; exit 1; \
	fi; \
	echo "gofmt clean"

## check: fmt-check, vet and test — what CI should run
check: fmt-check vet test

## image: build the container image published by container.yml
image:
	docker build --file Dockerfile --target base --tag $(BINARY):dev .

## toolchain: report which toolchain would be used
toolchain:
	@echo "$(TOOLCHAIN)"
	@echo "target: $(HOST_GOOS)/$(HOST_GOARCH)"

## clean: remove the binary and the Go caches
clean:
	rm -f $(BINARY) $(BINARY).exe
	chmod -R u+w $(CACHE_DIR) 2>/dev/null || true
	rm -rf $(CACHE_DIR)

## help: list every target
help:
	@echo "Targets:"
	@grep -E '^## [a-z-]+:' $(MAKEFILE_LIST) \
		| sed -e 's/^## //' -e 's/:/\t/' \
		| awk -F'\t' '{printf "  %-12s %s\n", $$1, $$2}'
	@echo
	@echo "Toolchain: $(TOOLCHAIN)"
	@echo "Set GO_DOCKER=1 to force the container path, GO_VERSION to pick"
	@echo "the image tag (currently $(GO_IMAGE))."

$(CACHE_DIR):
	@mkdir -p $(CACHE_DIR)
