![GitHub Workflow Status](https://img.shields.io/github/workflow/status/vlang/docker/Deploy%20nightly%20build%20to%20Dockerhub) 
![Docker Pulls](https://img.shields.io/docker/pulls/thevlang/vlang)
![Docker Image Size (latest by date)](https://img.shields.io/docker/image-size/thevlang/vlang)

# V programming language docker images source (Work in progress)
The docker files for the V programming language. Please check individual `Dockerfile` for what is provided in detail

Works both with docker for linux and windows on x86 plattform.

## WIP

- [x] Basic images and nightly builds
- [ ] Provide examples of usage (vweb)

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

### Running the standard image

Running the development image using iteractive terminal.

```bash
docker run \
  -it \
  --name v-container \
  thevlang/vlang \
  /bin/bash
```

### Running the development image

Running the development image using iteractive terminal and mapping current directory to internal /src directory.
```bash
docker run \
  -it \
  -v ${PWD}:/src \
  --name v-dev-container \
  thevlang/vlang:alpine-dev \
  /bin/sh
```


# Different images being built

Following images are built from this repo:

| tag             |       Description |
| --------------- | ----------------- |
| latest          | Nightly build of latest V on Debian Buster|
| \[githash\]     | The sha commit id built (soon supported)|
| buster          | Nightly build of latest V on Debian Buster|
| alpine          | Nightly build of latest V on Alpine 3.11 |
| ubuntu          | Nightly build of latest V on Ubuntu 20.04|
| runtime-scratch | Minimal size scratch based image with runtime dependencies (soon supported)|
| \[dist\]-build  | Used in V CI builds to build V itself. No V included in image.|
| \[dist\]-dev  | Development build with all development dependecies on distributions.|

## OS specific base images

OS specific base images are built for specific distributions. They are named `[dist]-base`.
