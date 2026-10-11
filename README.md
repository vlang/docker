![Build and deploy the nightly images](https://github.com/vlang/docker/actions/workflows/nightly_builds.yml/badge.svg)
[![Docker Pulls](https://img.shields.io/docker/pulls/thevlang/vlang)](https://hub.docker.com/r/thevlang/vlang)
[![Docker Image Size (latest by date)](https://img.shields.io/docker/image-size/thevlang/vlang)](https://hub.docker.com/r/thevlang/vlang/tags?page=1&ordering=last_updated)

# The `thevlang/vlang` images

The Dockerfiles for the `thevlang/vlang` images on Docker Hub, and the workflows
that publish them.

Everything here works with **Docker** or **Podman**: the build files are
`Dockerfile*` and Podman reads Dockerfiles natively, so no conversion is needed.

## The variants

An official image has to answer one question first: *can it build programs?* V
is a compiler that emits C and then invokes a C compiler, so an image without a
C compiler can only run things that were compiled elsewhere.

| Tag | Base image | C library | C compiler | Use it for |
| --- | --- | --- | --- | --- |
| `:latest` / `:debian` | `debian-base` | glibc | gcc | the default: a glibc binary built here runs on Debian, Ubuntu, Fedora and derivatives |
| `:alpine` | `alpine-base` | musl | gcc | small images, and static executables (`-cflags -static`) |
| `:nix` | `nixos/nix` | glibc | gcc | a pinned nixpkgs toolchain; `nix-shell -p <pkg>` works inside |
| `:static` | `scratch` | none | none | `v version`, and as a base for a static V program |
| `:<dist>-dev` | the `-build` image | as above | as above | a working V checkout, for working on V itself |
| `:<dist>-build` | the `-base` image | as above | alpine and nix ship gcc; debian and ubuntu ship clang and no gcc | the intermediate images the Dockerfiles stand on |
| `:<dist>-base` | the distro image | as above | none | the minimal dependencies layer, with no compiler of its own |

`:debian`, `:alpine` and `:nix` are floating tags tracking V master, rebuilt
nightly. Every variant is published for both `linux/amd64` and `linux/arm64`.
`:static` is published as `:static` by the nightly workflow. The `:<version>`
tags do not exist yet — they come from a release job in `vlang/v` that is part of
an open change there (see below), so until that lands the only tags are the
floating ones.

`:debian` and `:alpine` differ in more than the package manager: the `:debian`
image is glibc, so a program you compile in it runs on Debian, Ubuntu, Fedora
and their derivatives, while the `:alpine` image is musl and its binaries run on
Alpine. Pick by where the program has to run, not by which one you find more
familiar.

## Using the images

### Run V on the code in the current directory

```bash
docker run --rm -it -v "$PWD":/src -w /src thevlang/vlang:latest v run main.v
```

`/src` is the working directory in every runtime image, so mounting your project
there is all the setup there is. On Windows, use `%CD%` instead of `"$PWD"`. The
`-base`, `-build` and `ubuntu-*` images use `/opt/vlang` instead, because they
are build and CI images rather than anything you mount code into.

### An interactive shell

```bash
docker run --rm -it -v "$PWD":/src -w /src thevlang/vlang:alpine sh
```

### Run a single command without a shell

```bash
docker run --rm thevlang/vlang:latest v version
docker run --rm thevlang/vlang:latest v fmt -verify .
```

### Where V writes

V creates a module cache and temporary files, so it needs a writable home:

| Variable | Default in these images | Why it matters |
| --- | --- | --- |
| `HOME` | `/root`, except `:static` where it is `/tmp` | `~/.vmodules` and the tool cache live here |
| `VTMP` | unset in every variant but `:static`, where it is `/tmp/v` | V's temp directory; set it to a writable path in read-only containers |
| `VMODULES` | unset in every variant but `:static`, where it is `/tmp/vmodules` | where `v install` puts modules |

In `:static` there is no writable `/root`, so `HOME` is set to `/tmp` — keep that
in mind if you override the environment.

### Docker Compose

```yml
services:
  v:
    image: thevlang/vlang:alpine
    tty: true
    volumes:
      - .:/src
    working_dir: /src
```

```bash
docker compose run --rm v v run main.v
docker compose exec v sh
```

## The `:static` image

`FROM scratch`, so: no libc, no loader, no shell, no C compiler. It contains a
statically linked V compiler and `vlib`.

```bash
# Works, because it needs nothing but the binary itself:
docker run --rm thevlang/vlang:static v version

# Does not work. The first error is not the missing compiler but the missing
# Boehm GC library, which V's default GC mode wants before it reaches a C
# compiler; `-gc none` gets past that and then stops on the compiler.
docker run --rm thevlang/vlang:static v run main.v
```

Its real use is as a base image for a program you have already compiled:

```dockerfile
FROM thevlang/vlang:static
COPY --from=build /app/program /usr/local/bin/program
CMD ["program"]
```

Build the program in a variant that *has* a compiler:

```bash
docker run --rm -v "$PWD":/src -w /src thevlang/vlang:alpine \
  v -prod -cc gcc -cflags -static -o program main.v
```

The image is 78.6 MB compressed, against roughly 100 MB for the debian and
alpine runtime images, so it is the smallest published V. `v fmt`, `v doc` and
the other subcommands are not included, because they are driven by building
`cmd/tools/<tool>` from a source tree at run time (see `find_vroot` and
`launch_external_tool` in `cmd/v/v.v`), which needs both a compiler and a
checkout — verified: `v fmt` fails with `the V source tree could not be found`.

## The `:nix` image

The toolchain comes from **one pinned nixpkgs revision**
(`NIXPKGS_REV`, currently `39ad350a...`, 2026-10-07) instead of from
`apk add`/`apt install`:

```bash
docker run --rm thevlang/vlang:nix v version
```

The practical difference is what you can do *inside* the container: a nixpkgs
library can be made available at build time, where on the other variants it
would be a second base image:

```bash
docker run --rm -v "$PWD":/src -w /src thevlang/vlang:nix \
  sh -c 'nix-shell -p openssl sqlite --run "v run main.v"'
```

Bumping the pin is the only way the *toolchain* changes, so the compiler and
libraries are the same from one build to the next. The base image is
`nixos/nix:latest` and still floats, so "reproducible" here means the toolchain,
not the whole rootfs. To build against a different pin:

```bash
docker build -t vlang-nix-pinned \
  --build-arg NIXPKGS_REV=<nixpkgs-commit> \
  -f docker/vlang/Dockerfile.nix.build .
```

Note that `nixos/nix` is not available in every region; if a pull fails with a
CloudFront 403, build `docker/vlang/Dockerfile.nix` on a host that can reach it,
or install Nix yourself and use the `devShell` in `nix/flake.nix`.

## Building the images yourself

The build files are ordinary Dockerfiles, so Docker and Podman both read them.
Every V image this repository publishes takes the revision to build. The one
exception is `Dockerfile.ubuntu`, which predates the `V_REV` argument and still
clones whatever master is at build time:

| Build arg | Default | Meaning |
| --- | --- | --- |
| `V_REV` | `master` | a branch, tag or commit of [vlang/v](https://github.com/vlang/v) |
| `NIXPKGS_REV` | the pinned revision | the nixpkgs commit the `nix` variants use |
| `USER` | `thevlang` | the Docker Hub namespace the intermediate images live under |

```bash
# the variant you will probably want
docker build -t vlang-nix -f docker/vlang/Dockerfile.nix .

# a specific release, rather than master
docker build --build-arg V_REV=0.5.2 -t vlang-0.5.2 -f docker/vlang/Dockerfile.alpine .

# the static image
docker build -t vlang-static -f docker/vlang/Dockerfile.static .
```

Building `Dockerfile.alpine` and `Dockerfile.debian` needs the matching `-base`
and `-build` images, and `Dockerfile.nix` needs `nix-build` — both of its stages
stand on that one image, so it has no `-base`. Either pull them, or build them
first. The namespace has to match on every step, which is what `--build-arg
USER=` is for:

```bash
docker build -t myuser/vlang:alpine-base -f docker/base/Dockerfile.alpine .
docker build --build-arg USER=myuser -t myuser/vlang:alpine-build -f docker/vlang/Dockerfile.alpine.build .
docker build --build-arg USER=myuser -t vlang-alpine -f docker/vlang/Dockerfile.alpine .
```

### Multi-arch

The published images are `linux/amd64` + `linux/arm64`. A multi-arch build needs
a builder that can emulate the other architecture:

```bash
docker run --privileged --rm tonistiigi/binfmt --install all
docker buildx create --name multi --driver docker-container --use
docker buildx build --platform linux/amd64,linux/arm64 \
  -t thevlang/vlang:nix --push -f docker/vlang/Dockerfile.nix .
```

A `docker-container` driver is required: the default builder cannot produce a
multi-platform manifest. Use `--load` instead of `--push` to keep the result in
the local image store.

Emulation is slow — a full V build under QEMU takes a long time — so prefer
native builders for anything you run often. If you already have separate
per-arch images and no registry, `regctl index create` writes an OCI image index
into a local `oci:` layout without a daemon:

```bash
regctl index create ocidir://layout:index \
  --ref ocidir://layout:amd64 --platform linux/amd64 \
  --ref ocidir://layout:arm64 --platform linux/arm64
```

## Podman

Podman reads the same files. There is no daemon and no root required:

```bash
podman build -t vlang-nix -f docker/vlang/Dockerfile.nix .
podman run --rm -v "$PWD":/src -w /src vlang-nix v run main.v
```

The practical differences:

| | Docker | Podman |
| --- | --- | --- |
| Build engine | BuildKit, via a daemon | Buildah, forked per build; `podman buildx build` is only a compatibility alias |
| Containers run as | root unless you say `--user` | your own UID by default |
| Volume mounts | owned by root inside the container | owned by your UID, because it is your UID |
| Multi-arch | `--platform`, via a `docker-container` builder | `--platform`, with `qemu-user-static` + `binfmt` on the host |
| Registry names | short names resolve to `docker.io` | short names may be fully qualified in `registries.conf` |

Two consequences worth knowing:

- **No root daemon** means no `sudo docker`, and a build that dies does not
  leave an orphaned daemon holding your ports.
- **Rootless mounts** mean a file your container writes appears as *yours* on
  the host. With Docker you get root-owned files and `chown` afterwards. This is
  the main reason to prefer Podman for a mounted source directory.

Multi-arch with Podman:

```bash
sudo dnf install qemu-user-static   # or: apt install qemu-user-static binfmt-support
podman build --platform linux/amd64,linux/arm64 -t vlang-nix -f docker/vlang/Dockerfile.nix .
podman manifest create vlang-nix:latest
podman manifest add vlang-nix:latest containers-storage:localhost/vlang-nix
podman manifest push vlang-nix:latest docker://myregistry/vlang:latest
```

## Publishing

| Workflow | Trigger | What it publishes |
| --- | --- | --- |
| `base.yml` | push to `master`, PR, manual | `:<dist>-base` |
| `build.yml` | push to `master`, PR, manual | `:<dist>-build` |
| `build_ubuntu.yml` | push to `master`, PR, manual | `:ubuntu-base`, `:ubuntu-build` |
| `nightly_builds.yml` | daily 02:00 UTC, push, PR | `:latest`, `:debian`, `:alpine`, `:nix`, `:static`, and every `:<dist>-dev` |
| [vlang/v `hub_docker_ci.yml`](https://github.com/vlang/v/blob/master/.github/workflows/hub_docker_ci.yml) (changed by [vlang/v#29883](https://github.com/vlang/v/pull/29883), still open) | a V release tag, or `workflow_dispatch` | **not yet live.** As of today that workflow builds only `debian` and `alpine`, from V master, and pushes only `:latest`, `:debian`, `:alpine`, `:debian-dev` and `:alpine-dev` — no `nix`, no `static`, no version tag. #29883 is what makes it pass `V_REV` and add the other two, so everything in the version-tag column above describes the state *after* it merges |

Pushes require `DOCKER_USERNAME` and `DOCKER_TOKEN` secrets. `vars.PLATFORMS`
and `vars.DOCKER_REPOSITORY` override the default platforms and namespace; the
workflows fall back to `linux/amd64,linux/arm64` and `thevlang` when the
variables are unset.

Pull requests build but never push, and the login step is skipped for them, so a
fork can validate its changes.
