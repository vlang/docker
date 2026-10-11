# V built from source on a Nix-pinned toolchain.
#
# The toolchain comes from one pinned nixpkgs revision, so it is
# reproducible in a way `apk add` / `apt install` never is. The base
# image still floats, so the rootfs is not pinned.
#
# Generated from manifest.json by render.py. Do not edit by hand.
ARG USER=thevlang
ARG V_REV=master

FROM ${USER}/vlang:nix-build AS builder

ARG V_REV

WORKDIR /opt/vlang

RUN git clone --depth 1 https://github.com/vlang/v . && \
    git fetch --quiet --depth 1 origin "${V_REV}" && \
    git checkout --quiet FETCH_HEAD && \
    make VFLAGS='-cc gcc' && v -version


FROM ${USER}/vlang:nix-build AS runtime

COPY --from=builder /opt/vlang /opt/vlang

# Clamp every timestamp so two builds of the same commit produce the
# same image. `git clone` and `make` both stamp files with the wall
# clock, and COPY bakes that into the layers.
ARG SOURCE_DATE_EPOCH=1735689600
RUN find /opt/vlang -exec touch -h -d @${SOURCE_DATE_EPOCH} {} + && \
    newer=$(find /opt/vlang -newermt @${SOURCE_DATE_EPOCH} -print -quit) && \
    if [ -n "$newer" ]; then \
        echo >&2 "timestamps not clamped: $newer"; exit 1; \
    fi && \
    echo "clamped to $SOURCE_DATE_EPOCH"

LABEL org.opencontainers.image.title="thevlang/vlang:nix"
LABEL org.opencontainers.image.description="The V language on a pinned nixpkgs toolchain, with a C compiler so V can still build programs"
LABEL org.opencontainers.image.source=https://github.com/vlang/docker
LABEL org.opencontainers.image.licenses=MIT

ENV VFLAGS="-cc gcc"

WORKDIR /src

