![GitHub Workflow Status](https://img.shields.io/github/workflow/status/vlang/docker/Deploy%20nightly%20build%20to%20Dockerhub) 
[![Docker Pulls](https://img.shields.io/docker/pulls/thevlang/vlang)](https://hub.docker.com/r/thevlang/vlang)
[![Docker Image Size (latest by date)](https://img.shields.io/docker/image-size/thevlang/vlang)](https://hub.docker.com/r/thevlang/vlang/tags?page=1&ordering=last_updated)

# V programming language docker images source (Work in progress)

The docker files for the V programming language. Please check individual `Dockerfile` for what is provided in detail

Works both with docker for linux and windows on x86 plattform.

## WIP

- [x] Basic images 
- [ ] Get nightly builds working
- [ ] Provide examples of usage (vweb @smartiniOnGitHub example)

## Structure

| folder          | Description                                         |
| --------------- | --------------------------------------------------- |
| base/os         | Docker files for supported os. Minimal dependencies |
| vlang           | Docker files for `thevlang/vlang` images            |

## Structure of the image

The images are deployed as `thevlang/vlang:tag`. 


# Usage

## 1. Installing docker

[Here are installation instructions on ubuntu](https://docs.docker.com/engine/install/ubuntu/) but there are instructions for other distributions too.

## 2 Running the image

### Choose your image

Browse [thevlang/vlang](https://hub.docker.com/r/thevlang/vlang/tags?page=1&ordering=last_updated) on Docker Hub and choose your tag.

### Running the standard image

Running the development image using iteractive terminal.

```bash
docker run \
  --rm \
  -it \
  --name v-container \
  thevlang/vlang \
  /bin/bash
```

### Running the development image

Running the development image using iteractive terminal and mapping current directory to internal /src directory.
```bash
docker run \
  --rm \
  -it \
  -v ${PWD}:/src \
  --name v-dev-container \
  thevlang/vlang:alpine-dev \
  /bin/sh
```

### Using Docker Compose

Creating a container ready to go in.

```yml
version: "3"
services:
  v:
    image: thevlang/vlang:alpine
    tty: true # Keeps your container running
    volumes:
      - .:/src
    working_dir: /src
```

Use it:

```bash
you@pc > docker compose exec v sh
$ v --version
V 0.3.3 a938dcd
```

Creating a disposable container.

```yml
version: "3"
services:
  v:
    image: thevlang/vlang:alpine
    entrypoint: v
    volumes:
      - .:/src
    working_dir: /src
```

Use it:

```bash
you@pc > docker compose run v --version
V 0.3.3 a938dcd
```


# Different images being built

Following images are built from this repo:

| tag             |       Description |
| --------------- | ----------------- |
| latest          | Nightly build of latest V on Debian latest|
| \[githash\]     | The sha commit id built (soon supported)|
| alpine          | Nightly build of latest V on Alpine latest|
| debian          | Nightly build of latest V on Debian latest|
| ubuntu          | Nightly build of latest V on Ubuntu latest|
| runtime-scratch | Minimal size scratch based image with runtime dependencies (soon supported)|
| \[dist\]-build  | Used in V CI builds to build V itself. No V included in image.|
| \[dist\]-dev    | Development build with all development dependencies on distributions.|


# Note

## Manually build images

In this repository there are many Dockerfiles; to build images manually (for example to develop/debug/test them), do something like:
- choose an OS, for example Debian
- create the base image:
```
docker pull debian # force a pull, could be useful if already downloaded but not updated recently
docker build -t thevlang/vlang:debian-base -f ./docker/base/os/debian/Dockerfile.debian .
```
by default 'latest' OS image is used.
To build with a specific OS release, specify it as a build argument, for example:
```
docker build --build-arg OS_RELEASE=buster -t thevlang/vlang:debian-base -f ./docker/base/os/debian/Dockerfile.debian .
```
- create the build image (with all dependencies inside):
```
docker build -t thevlang/vlang:debian-build -f ./docker/vlang/Dockerfile.debian.build .
```
- create the dev-full image (with V built inside):
```
docker build -t thevlang/vlang:debian-dev -f ./docker/vlang/Dockerfile.debian.dev-full .
```
- run the dev-full image, to ensure it's good:
```
docker run --rm -it thevlang/vlang:debian-dev
# inside it for example run:
v --version
exit

# mount current folder
docker run --rm -it -v $(pwd):/src thevlang/vlang:debian-dev
# then try to build/test/run them ...
exit
```

## Old images

Previous images (already published) had OS code name in the image tag, but are no more created/updated; please do not use them anymore.


----
