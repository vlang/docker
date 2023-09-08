# vweb runtime example

Create a `Dockerfile` with the following content in the root of your project: 

```Dockerfile 
from thevlang/vlang:alpine-build as base

RUN apk update
RUN apk add postgresql-dev

from base as build

RUN mkdir -p /home/vlang

WORKDIR /home/vlang/

COPY v.mod .
COPY src src
COPY static static

# Install repo dependencies
RUN v install
RUN v -prod -o vweb-app .

RUN ls

RUN pwd

from base as runtime

WORKDIR /home/vlang
COPY --from=build /home/vlang/vweb-app .
COPY static static

EXPOSE 8081

ENTRYPOINT ["./vweb-app"]
```

Now you can build it with `docker built -t test .` and run it with `docker run test --rm --port 8081:8081`

## Features

- [x] Multi-stage build of image
- [x] Compressed binary


## Other examples
*  [west_sample](https://github.com/Dracks/west_sample/): you can see here a project with github workflows configured of how to generate a docker image of a V project and publish it into docker hub
