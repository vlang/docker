FROM thevlang/vlang:alpine as builder
WORKDIR /srv
COPY . .
RUN ["v", "-o", "server", "."]

FROM alpine

# If one wants to use built-in sqlite lib :)
RUN ["apk", "add", "sqlite-libs"]

COPY --from=builder /srv/server .
CMD ["/server"]
