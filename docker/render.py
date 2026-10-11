#!/usr/bin/env python3
"""Render the Dockerfiles under docker/ from manifest.json.

Every fact about a published image lives in the manifest, so a runtime image's
FROM chain cannot disagree with the variant's name. That is the bug this
replaces: `Dockerfile.debian` used to be `FROM thevlang/vlang:alpine-build`, so
`:debian` and `:alpine` were the same image and the tag meant only the name.

    python docker/render.py           write every Dockerfile
    python docker/render.py --check   write nothing; fail if any file differs

`--check` is the one CI runs. It is the guard against a hand-edited Dockerfile
drifting from the manifest, which is exactly how the `alpine`/`debian` collapse
and the missing Boehm GC both survived review: the files looked individually
plausible.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # docker/
ROOT = HERE.parent                              # the repository
MANIFEST = HERE / "manifest.json"

# Line width the generated comment blocks wrap to.
WIDTH = 78

BSL = "\\"

def load() -> dict:
    with MANIFEST.open(encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- helpers

def vpkg(variant: dict, arch: str, arches: dict) -> str:
    """The package-manager name of one architecture for one variant."""
    family = {"apk": "apk", "apt": "dpkg"}[variant["pkg_manager"]]
    return arches[arch][family]


def as_comment_map(comments) -> dict:
    """Accept either `{pkg: note}` or `[[pkg, note], ...]` from the manifest."""
    if not comments:
        return {}
    if isinstance(comments, dict):
        return comments
    return {pkg: note for pkg, note in comments}


def apk_line(packages: list[str], comments=None) -> list[str]:
    """`apk --no-cache add pkg...` with `# note` comments the way the repo writes it."""
    if not packages:
        return []
    notes = as_comment_map(comments)
    out = ["RUN apk --no-cache add \\"]
    body = []
    for pkg in packages:
        note = notes.get(pkg)
        if note:
            body.append(f"    # {note}")
        body.append(f"    {pkg} \\")
    # drop the trailing continuation from the last real line
    body[-1] = body[-1][:-2]
    out.extend(body)
    return out


def apt_install(packages: list[str], *, indent: str = "  ",
                chained: bool = False) -> list[str]:
    """`apt-get install -y --no-install-recommends pkg...`, one per line.

    `chained` puts `&&` before the final backslash, so the line after the
    packages is the next shell command rather than another package name.

    Without it the trailing backslash lands on the last package and continues
    the *apt* command, which swallows whatever follows as an argument - the build
    then fails with "E: Unable to locate package apt-get", which names the
    symptom rather than the cause.
    """
    lines = [f"{indent}apt-get install -y --no-install-recommends \\"]
    for i, p in enumerate(packages):
        last = i == len(packages) - 1
        tail = " && \\" if (last and chained) else (" \\" if not last else "")
        lines.append(f"{indent}    {p}{tail}")
    return lines


def wrap(text: str, prefix: str = "# ") -> list[str]:
    words, lines, cur = text.split(), [], prefix.rstrip()
    for w in words:
        if len(cur) + 1 + len(w) > WIDTH:
            lines.append(cur.rstrip())
            cur = prefix + w
        else:
            cur += " " + w
    if cur.strip() and cur.strip() != prefix.strip():
        lines.append(cur.rstrip())
    return lines


def comment_block(text: str) -> list[str]:
    return wrap(text)


# ---------------------------------------------------------------- renderers

def render_base(m: dict, name: str, v: dict) -> str:
    """docker/base/Dockerfile.<name> - distro plus the minimal deps."""
    o = m["organisation"]
    L = []
    L.append(f"# This is the dockerfile for generating base images for {name}")
    L.append("# contains the minimal dependencies needed for V to run")
    L.append(f"FROM {v['base']}")
    L.append("")
    L.append('LABEL org.opencontainers.image.source=' + m["source"])
    if name == "debian":
        L.append(f'LABEL org.opencontainers.image.title="{o}/vlang:{name}-base"')
    if name == "alpine":
        L.append(f'LABEL org.opencontainers.image.title="{o}/vlang:{name}-base"')
    L.append("")
    L.append("WORKDIR " + m["vroot"])
    L.append("")
    L.append(f"ENV VVV {m['vroot']}")
    L.append(f"ENV PATH {m['vroot']}:/usr/local/sbin:/usr/local/bin:/usr/sbin:"
             "/usr/bin:/sbin:/bin")
    L.append("")
    L.append(f"RUN mkdir -p {m['vroot']} && ln -s {m['vroot']}/v /usr/bin/v")
    L.append("")
    if v["pkg_manager"] == "apk":
        L.append("RUN apk update && \\")
        L.append("    # Default base dependencies")
        L.append("    apk add --no-cache " + " ".join(v["base_packages"]))
    else:
        L.append("RUN apt-get update && \\")
        L.append("    DEBIAN_FRONTEND=noninteractive && \\")
        L.append("    # Default base dependencies")
        L.append("    apt-get install -y --no-install-recommends "
                 + " ".join(v["base_packages"]) + " && \\")
        L.append("    apt-get clean && rm -rf /var/cache/apt/archives/* && \\")
        L.append("    rm -rf /var/lib/apt/lists/*")
    L.append("")
    return "\n".join(L) + "\n"


def render_build(m: dict, name: str, v: dict) -> str:
    """docker/vlang/Dockerfile.<name>.build - the toolchain, no V."""
    o = m["organisation"]
    L = []
    L.append(f"# Builder image with {name} base, used as the builder stage")
    L.append("# for multi-stage builds. Also the base for the full dev image.")
    L.append("")
    L.append("ARG USER=" + o)
    if "nixpkgs_rev" in v:
        L.append(f"FROM {v['base']}")
        L.append("")
        L.append("# Declared inside the build stage on purpose: an ARG declared before")
        L.append("# the first FROM is not in scope after it, so a global declaration would")
        L.append("# substitute an empty string into the URL below.")
        L.append(f"ARG NIXPKGS_REV={v['nixpkgs_rev']}")
        L.append("")
        L.append("ENV NIXPKGS_REV=${NIXPKGS_REV}")
        L.append("")
        L.append(f'LABEL org.opencontainers.image.title="{o}/vlang:{name}-build"')
        L.append('LABEL org.opencontainers.image.description="Nix toolchain image '
                 'for building V from source"')
        L.append(f'LABEL org.opencontainers.image.source={m["source"]}')
        L.append(f'LABEL org.opencontainers.image.licenses={m["licenses"]}')
        L.append('LABEL org.opencontainers.image.version=${NIXPKGS_REV}')
        L.append("")
        L.append("# `nix-env -f <tarball> -iA ...` installs from one pinned nixpkgs")
        L.append("# commit, with no channel in the way, so the same NIXPKGS_REV always")
        L.append("# yields the same store paths.")
        pkgs = " ".join(v["build_packages"])
        L.append(f'RUN nix-env -f "https://github.com/NixOS/nixpkgs/archive/'
                 '${NIXPKGS_REV}.tar.gz" -iA \\')
        for pkg in v["build_packages"]:
            L.append(f"    {pkg} \\")
        L[-1] = L[-1][:-2]
        L.append("")
        L.append("# `nix-env -i` as root installs into /root/.nix-profile, which the")
        L.append("# base image does not already put on PATH.")
        L.append("ENV PATH=/root/.nix-profile/bin:/nix/var/nix/profiles/default/bin:"
                 "/usr/bin:/bin")
        L.append("")
        L.append("WORKDIR " + m["vroot"])
        L.append("")
        L.append('CMD ["bash"]')
        L.append("")
        return "\n".join(L)

    L.append(f"FROM ${{USER}}/vlang:{name}-base" + (" AS builder" if name == "debian" else ""))
    L.append("")
    L.append(f'LABEL org.opencontainers.image.title="{o}/vlang:{name}-build"')
    L.append(f'LABEL org.opencontainers.image.source={m["source"]}')
    L.append(f'LABEL org.opencontainers.image.licenses={m["licenses"]}')
    L.append("")
    L.append("WORKDIR " + m["vroot"])
    L.append("")
    if v["pkg_manager"] == "apk":
        L.extend(apk_line(v["build_packages"], v.get("package_comments", {}).get("build")))
    else:
        L.append("RUN apt-get update && \\")
        L.extend(apt_install(v["build_packages"], indent="    ", chained=True))
        deferred = v.get("build_packages_deferred")
        if deferred:
            # No blank line here: this is all one RUN continuation, and a blank
            # line ends it, which turns the next line into a Dockerfile
            # instruction. That is how `wget` became an instruction and the file
            # stopped parsing.
            L.append(f"    # {deferred['note']}")
            L.append(f"    {deferred['command']} && \\")
            L.append("    apt-get update && \\")
            L.extend(apt_install(deferred["packages"], indent="    ", chained=True))
        L.append("    apt-get clean && rm -rf /var/cache/apt/archives/* && \\")
        L.append("    rm -rf /var/lib/apt/lists/*")
    L.append("")
    return "\n".join(L) + "\n"


def clamp_timestamps(m: dict, v: dict, paths: list[str]) -> list[str]:
    """Clamp mtimes so two builds of one commit give the same image.

    Go does this in Dockerfile-linux.template and then *asserts* it in the build.
    Without the assertion a `touch` that silently failed would leave the image
    non-reproducible while every check said it was fine, which is exactly the
    shape of bug this whole manifest exists to remove.
    """
    epoch = m.get("source_date_epoch")
    if not epoch:
        return []
    if v.get("layout") == "static":
        # A `FROM scratch` stage has no shell, so there is nothing to run the
        # clamp: COPY stamps its files with the build time and the final stage
        # cannot correct it. debian, alpine and nix are reproducible; this one
        # is not, and the reason is structural rather than an omission.
        return []
    joined = " ".join(paths)
    return [
        "# Clamp every timestamp so two builds of the same commit produce the",
        "# same image. `git clone` and `make` both stamp files with the wall",
        "# clock, and COPY bakes that into the layers.",
        f"ARG SOURCE_DATE_EPOCH={epoch}",
        f"RUN find {joined} -exec touch -h -d @${{SOURCE_DATE_EPOCH}} {{}} + && \\",
        f"    newer=$(find {joined} -newermt @${{SOURCE_DATE_EPOCH}} -print -quit) && \\",
        '    if [ -n "$newer" ]; then \\',
        '        echo >&2 "timestamps not clamped: $newer"; exit 1; \\',
        '    fi && \\',
        '    echo "clamped to $SOURCE_DATE_EPOCH"',
    ]


def arch_case(m: dict, v: dict, indent: str = "    ") -> list[str]:
    """Runtime architecture detection, the way Go's and Rust's Dockerfiles do it.

    One Dockerfile then serves every architecture instead of relying on
    `buildx --platform`, which is a different and untested code path for a local
    `docker build` on arm64. The mapping is per package manager, because Alpine
    and Debian do not spell the same architecture the same way.
    """
    arches = m["arches"]
    family = {"apk": "apk", "apt": "dpkg"}[v["pkg_manager"]]
    probe = "apk --print-arch" if family == "apk" else "dpkg --print-architecture"
    out = ["# Detect the build architecture at build time, so one Dockerfile serves",
           "# every variant instead of relying on buildx --platform. Alpine and",
           "# Debian do not spell the same architecture the same way."]
    out.append("RUN set -eu; \\")
    out.append(f"{indent}arch=\"$({probe})\"; \\")
    out.append(f"{indent}case \"$arch\" in \\")
    for a in v["arches"]:
        out.append(f"{indent}    {arches[a][family]}) echo \"building for {a}\" ;; \\")
    out.append(f"{indent}    *) echo >&2 \"unsupported architecture: $arch\"; exit 1 ;; \\")
    out.append(f"{indent}esac")
    return out


def render_runtime(m: dict, name: str, v: dict) -> str:
    """docker/vlang/Dockerfile.<name> - the published runtime image."""
    o = m["organisation"]
    arches = m["arches"]
    L = []

    if name == "slim":
        # Same builder as `static`, but only the compiler is carried across: no
        # vlib, no C compiler, no package manager. The smallest V runtime.
        L.append("# The smallest V runtime: a scratch image that runs one")
        L.append("# already-compiled static V program.")
        L.append("#")
        L.append("# There is deliberately nothing else in here. No vlib, no C")
        L.append("# compiler, no package manager, no shell. Compile your program in")
        L.append("# `alpine` or `debian` first, with `-cflags -static` so it links")
        L.append("# statically - otherwise there is no loader for it to start.")
        L.append("#")
        L.append("#   docker build -t myapp - <<'EOF'")
        L.append("#   FROM thevlang/vlang:slim")
        L.append("#   COPY --from=build /app/program /app/program")
        L.append("#   CMD [\"/app/program\"]")
        L.append("#   EOF")
        L.append("#")
        L.append("# Generated from manifest.json by render.py. Do not edit by hand.")
        L.append(f"ARG V_REV={m['default_v_rev']}")
        L.append("")
        L.append(f"FROM {v['builder_base']} AS builder")
        L.append("")
        L.append("RUN apk --no-cache add " + " ".join(v["builder_packages"]))
        L.append("")
        L.append("WORKDIR " + m["vroot"])
        L.append("ARG V_REV")
        L.append("")
        L.append("RUN git clone --depth 1 https://github.com/vlang/v . && \\")
        L.append("    git fetch --quiet --depth 1 origin \"${V_REV}\" && \\")
        L.append("    git checkout --quiet FETCH_HEAD && \\")
        L.append(f"    make {v['build_make']} && \\")
        L.append("    ./v -version")
        L.append("")
        L.append("")
        L.append("FROM scratch")
        L.append("")
        L.append('LABEL org.opencontainers.image.title="' + o + '/vlang:' + name + '"')
        L.append(f'LABEL org.opencontainers.image.description="{v["description"]}"')
        L.append(f'LABEL org.opencontainers.image.source={m["source"]}')
        L.append(f'LABEL org.opencontainers.image.licenses={m["licenses"]}')
        L.append("")
        L.append("COPY --from=builder /opt/vlang/v /usr/local/bin/v")
        L.append("")
        L.append("ENTRYPOINT [\"/usr/local/bin/v\"]")
        L.append("")
        return "\n".join(L) + "\n"

    if name == "static":
        L.append("# Minimal `scratch`-based image holding a fully static V compiler.")
        L.append("#")
        L.append("# What it is for:")
        L.append("#   * A base image for an already-compiled static V program:")
        L.append("#       FROM thevlang/vlang:static")
        L.append("#       COPY --from=build /app/program /usr/local/bin/program")
        L.append("#       CMD [\"program\"]")
        L.append("#   * `v version`.")
        L.append("#")
        L.append("# What it is deliberately not: a compiler. There is no C compiler in")
        L.append("# this image and V shells out to one for every `v run` / `v build`, so")
        L.append("# those do not work here.")
        L.append("#")
        L.append("# Generated from manifest.json by render.py. Do not edit by hand;")
        L.append("# edit the manifest and re-render.")
        L.append(f"ARG V_REV={m['default_v_rev']}")
        L.append("")
        L.append("# Stage 1 - build a static V on Alpine/musl.")
        L.append(f"FROM {v['builder_base']} AS builder")
        L.append("")
        L.append("RUN apk --no-cache add " + " ".join(v["builder_packages"]))
        L.append("")
        L.append("WORKDIR " + m["vroot"])
        L.append("ARG V_REV")
        L.append("")
        L.append("RUN git clone --depth 1 https://github.com/vlang/v . && \\")
        L.append("    git fetch --quiet --depth 1 origin \"${V_REV}\" && \\")
        L.append("    git checkout --quiet FETCH_HEAD && \\")
        L.append(f"    make {v['build_make']} && \\")
        L.append("    ./v -version")
        L.append("")
        L.append("FROM scratch")
        L.append("")
        L.append("COPY --from=builder /opt/vlang/v /opt/vlang/v")
        L.append("COPY --from=builder /opt/vlang/vlib /opt/vlang/vlib")
        L.append("COPY --from=builder /opt/vlang/v.mod /opt/vlang/v.mod")
        L.append("")
        # After the copy, not before it: COPY does not preserve mtimes.
        L.extend(clamp_timestamps(m, v, ["/opt/vlang"]))
        L.append("")
        L.append(f'LABEL org.opencontainers.image.title="{o}/vlang:static"')
        L.append(f'LABEL org.opencontainers.image.description="{v["description"]}"')
        L.append(f'LABEL org.opencontainers.image.source={m["source"]}')
        L.append(f'LABEL org.opencontainers.image.licenses={m["licenses"]}')
        L.append("")
        L.append("# V writes its module cache and temp files under the home directory,")
        L.append("# which has to be writable - in this image that is /tmp. /opt/vlang")
        L.append("# goes on PATH so that `v` and the image's CMD resolve.")
        L.append("ENV PATH=/opt/vlang:/usr/local/sbin:/usr/local/bin:/usr/sbin:"
                 "/usr/bin:/sbin:/bin \\")
        L.append("    VEXE=/opt/vlang/v \\")
        L.append("    HOME=/tmp \\")
        L.append("    VMODULES=/tmp/vmodules \\")
        L.append("    VTMP=/tmp/v")
        L.append("")
        L.append("COPY --from=builder /etc/passwd /etc/passwd")
        L.append("COPY --from=builder /etc/group /etc/group")
        L.append("COPY --from=builder /etc/ssl/certs/ca-certificates.crt "
                 "/etc/ssl/certs/ca-certificates.crt")
        L.append("")
        L.append("WORKDIR /src")
        L.append("")
        L.append('CMD ["v", "version"]')
        L.append("")
        return "\n".join(L)

    # nix: both stages stand on the same toolchain image.
    if name == "nix":
        L.append("# V built from source on a Nix-pinned toolchain.")
        L.append("#")
        L.append("# The toolchain comes from one pinned nixpkgs revision, so it is")
        L.append("# reproducible in a way `apk add` / `apt install` never is. The base")
        L.append("# image still floats, so the rootfs is not pinned.")
        L.append("#")
        L.append("# Generated from manifest.json by render.py. Do not edit by hand.")
        L.append("ARG USER=" + o)
        L.append(f"ARG V_REV={m['default_v_rev']}")
        L.append("")
        L.append(f"FROM ${{USER}}/vlang:{name}-build AS builder")
        L.append("")
        L.append("ARG V_REV")
        L.append("")
        L.append("WORKDIR " + m["vroot"])
        L.append("")
        L.append("RUN git clone --depth 1 https://github.com/vlang/v . && \\")
        L.append("    git fetch --quiet --depth 1 origin \"${V_REV}\" && \\")
        L.append("    git checkout --quiet FETCH_HEAD && \\")
        L.append(f"    make {v['build_make']} && v -version")
        L.append("")
        L.append("")
        L.append(f"FROM ${{USER}}/vlang:{name}-build AS runtime")
        L.append("")
        L.append("COPY --from=builder /opt/vlang /opt/vlang")
        L.append("")
        # After the copy, not before it: COPY does not preserve mtimes.
        L.extend(clamp_timestamps(m, v, ["/opt/vlang"]))
        L.append("")
        L.append('LABEL org.opencontainers.image.title="' + o + '/vlang:' + name + '"')
        L.append(f'LABEL org.opencontainers.image.description="{v["description"]}"')
        L.append(f'LABEL org.opencontainers.image.source={m["source"]}')
        L.append(f'LABEL org.opencontainers.image.licenses={m["licenses"]}')
        L.append("")
        L.append(f'ENV VFLAGS="{v["runtime_vflags"]}"')
        L.append("")
        L.append("WORKDIR /src")
        L.append("")
        return "\n".join(L) + "\n"

    # alpine / debian: two stages, base + build.
    L.append(f"# The V language on {name.capitalize()}"
             + (", with a C compiler so V can still build programs." if name == "debian" else "."))
    if name == "debian":
        L.append("#")
        L.append("# This image is glibc-based, which is what makes it worth having next")
        L.append("# to Dockerfile.alpine: a glibc program linked here runs on Debian,")
        L.append("# Ubuntu, Fedora and their derivatives, where a musl binary from the")
        L.append("# Alpine image does not.")
    L.append("#")
    L.append("# Generated from manifest.json by render.py. Do not edit by hand;")
    L.append("# edit the manifest and re-render.")
    L.append("ARG USER=" + o)
    L.append(f"ARG V_REV={m['default_v_rev']}")
    L.append("")
    L.append("# Stage 1 - Build the V-compiler")
    L.append(f"FROM ${{USER}}/vlang:{name}-build AS builder")
    L.append("")
    L.append("# Redeclared here: an ARG declared before the first FROM is out of a")
    L.append("# build stage's scope, so it has to be repeated to be readable by RUN.")
    L.append("ARG V_REV")
    L.append("")
    L.append("WORKDIR " + m["vroot"])
    L.append("")
    note = v.get("build_cc_note")
    if note:
        # Before the RUN, not inside it: Docker strips full-line comments from
        # the token stream, so a comment inside a continuation still parses, but
        # it reads as if it were part of the shell command.
        L.extend(wrap(note))
    L.append("RUN git clone --depth 1 https://github.com/vlang/v /opt/vlang && \\")
    L.append("    git -C /opt/vlang fetch --quiet --depth 1 origin \"${V_REV}\" && \\")
    L.append("    git -C /opt/vlang checkout --quiet FETCH_HEAD && \\")
    L.append(f"    make {v['build_make']} && v -version")
    L.append("")
    L.append("# Stage 2 - the runtime.")
    L.append(f"FROM ${{USER}}/vlang:{name}-base AS runtime")
    L.append("")
    L.append('LABEL org.opencontainers.image.title="' + o + '/vlang:' + name + '"')
    L.append(f'LABEL org.opencontainers.image.description="{v["description"]}"')
    L.append(f'LABEL org.opencontainers.image.source={m["source"]}')
    L.append(f'LABEL org.opencontainers.image.licenses={m["licenses"]}')
    L.append("")
    L.append(f'ENV VFLAGS="{v["runtime_vflags"]}"')
    L.append("")
    if v.get("arch_check"):
        L.extend(arch_case(m, v))
        L.append("")
    if v["pkg_manager"] == "apk":
        L.extend(apk_line(v["runtime_packages"],
                          v.get("package_comments", {}).get("runtime")))
    else:
        L.append("RUN apt-get update && \\")
        L.extend(apt_install(v["runtime_packages"], indent="    ", chained=True))
        L.append("    apt-get clean && rm -rf /var/lib/apt/lists/*")
    L.append("")
    L.append("# Copy the prebuilt V compiler")
    L.append("COPY --from=builder /opt/vlang /opt/vlang")
    L.append("")
    # After the copy, not before it: COPY does not preserve mtimes. A clamp
    # in the builder stage is invisible in the shipped image - measured: the
    # builder was at the epoch while the image still showed the wall clock.
    L.extend(clamp_timestamps(m, v, ["/opt/vlang"]))
    L.append("")
    L.append("WORKDIR /src")
    L.append("")
    return "\n".join(L) + "\n"


def render_dev(m: dict, name: str, v: dict) -> str:
    """docker/vlang/Dockerfile.<name>.dev-full.

    The -build image with a V checkout built in place, so the container is a
    working tree rather than just a compiler.

    The three of these were near-identical and hand-maintained, which is the
    drift risk the manifest exists to remove: debian's described a compiler it
    did not install (clang, not gcc), and that fix landed in one file only.
    """
    o = m["organisation"]
    rel = "Dockerfile.nix" if v["layout"] == "nix" else "Dockerfile.alpine"
    L = []
    L.append("ARG USER=" + o)
    if v["layout"] == "nix":
        L.append("# Everything the toolchain image has, plus the full V source")
        L.append("# tree built in place, so the container is a working V checkout")
        L.append("# rather than just a compiler. Use it to hack on V itself:")
        L.append("#")
        L.append(f'#   docker run --rm -it -v "$PWD":/src {o}/vlang:{name}-dev sh')
        L.append("#")
        L.append("# Generated from manifest.json by render.py. Do not edit by hand.")
        L.append("FROM ${USER}/vlang:" + name + "-build")
    else:
        L.append(f"# Generates a development image based on {name.capitalize()}, with V")
        L.append("# compiled in place so the container is a working checkout rather")
        L.append("# than just a compiler.")
        L.append("#")
        L.append("# Generated from manifest.json by render.py. Do not edit by hand.")
        L.append(f"FROM @@USERN@@/vlang:{name}-build")
    L.append("")
    L.append('LABEL org.opencontainers.image.title="' + o + '/vlang:' + name + '-dev"')
    L.append(f'LABEL org.opencontainers.image.description="A working V checkout '
             f'on {name}, for working on V itself"')
    L.append('LABEL org.opencontainers.image.source=' + m["source"])
    L.append('LABEL org.opencontainers.image.licenses=' + m["licenses"])
    L.append('LABEL org.opencontainers.image.authors="helto4real '
             '<helto4real@joysoftware.xyz>, Sandro Martini <sandro.martini@gmail.com>"')
    L.append("")
    L.append("# Which V revision is built; see " + rel + ".")
    L.append("ARG V_REV=" + m["default_v_rev"])
    L.append("ARG V_REV")
    L.append("")
    L.append("WORKDIR " + m["vroot"])
    L.append("")
    if v["layout"] == "nix":
        L.append("RUN git clone --depth 1 https://github.com/vlang/v . && " + BSL)
        L.append('    git fetch --quiet --depth 1 origin "${V_REV}" && ' + BSL)
        L.append("    git checkout --quiet FETCH_HEAD && " + BSL)
    else:
        L.append("RUN git clone --depth 1 https://github.com/vlang/v /opt/vlang && " + BSL)
        L.append('    git -C /opt/vlang fetch --quiet --depth 1 origin "${V_REV}" && ' + BSL)
        L.append("    git -C /opt/vlang checkout --quiet FETCH_HEAD && " + BSL)
    L.append("    make " + v["build_make"] + " && v -version && " + BSL)
    L.append("    mkdir /src")
    L.append("")
    L.append("WORKDIR /src")
    L.append("")
    return "\n".join(L) + "\n"


def render_all(m: dict) -> dict[str, str]:
    """Every file the manifest owns, as {relative path: content}."""
    out = {}
    for name, v in m["variants"].items():
        if "builder_base" in v:            # static: single self-contained file
            out[f"docker/vlang/Dockerfile.{name}"] = render_runtime(m, name, v)
            continue
        if v["layout"] == "nix":
            out[f"docker/vlang/Dockerfile.{name}.build"] = render_build(m, name, v)
            out[f"docker/vlang/Dockerfile.{name}"] = render_runtime(m, name, v)
            out[f"docker/vlang/Dockerfile.{name}.dev-full"] = render_dev(m, name, v)
            continue
        out[f"docker/base/Dockerfile.{name}"] = render_base(m, name, v)
        out[f"docker/vlang/Dockerfile.{name}.build"] = render_build(m, name, v)
        out[f"docker/vlang/Dockerfile.{name}"] = render_runtime(m, name, v)
        out[f"docker/vlang/Dockerfile.{name}.dev-full"] = render_dev(m, name, v)
    return out


def strip_comments(text: str) -> list[str]:
    """Dockerfile instructions with comment lines removed and blanks collapsed.

    The generator owns the prose: comments in a generated file are written from
    the manifest, so they cannot be a source of drift the way an instruction can.
    Comparing this instead of the raw bytes means a hand-edited comment does not
    fail the check, but a changed FROM, RUN, COPY or package list does - which is
    the class of bug this exists to catch.
    """
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        # A trailing comment inside a continuation is part of the instruction.
        out.append(line.rstrip())
    return out


NORMALISE = lambda b: b.replace(b"\r\n", b"\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="write nothing; fail if any file differs")
    args = ap.parse_args()

    m = load()
    files = render_all(m)

    drift = []
    for rel, content in sorted(files.items()):
        # rel is repository-relative ("docker/vlang/Dockerfile.debian"), so it
        # resolves against the repo root, not against docker/ - resolving it
        # against HERE makes the path not exist, and a check that reads nothing
        # always passes.
        path = ROOT / rel
        new = content.encode("utf-8")
        if path.exists():
            old = NORMALISE(path.read_bytes())
            # Compare instructions, not prose: the generator writes the comments,
            # so they cannot drift the way a FROM or a package list can.
            same = strip_comments(old.decode("utf-8")) == strip_comments(content)
            if not same:
                drift.append(rel)
            if not args.check:
                print(f"  {'DRIFT  ' if not same else 'ok     '} {rel}")
                path.write_bytes(new)
            else:
                print(f"  {'DRIFT  ' if not same else 'ok     '} {rel}")
        else:
            print(f"  NEW    {rel}")
            if not args.check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(new)

    if args.check and drift:
        print(f"\n{len(drift)} Dockerfile(s) differ from manifest.json:")
        for rel in drift:
            print(f"  {rel}")
        print("\nrun `python docker/render.py` to regenerate.")
        return 1
    if args.check:
        print(f"\n{len(files)} Dockerfiles match manifest.json")
        return 0
    print(f"\nwrote {len(files)} Dockerfiles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
