# SPDX-License-Identifier: GPL-2.0-only
let
  hostLock = builtins.fromJSON (builtins.readFile ../configs/build-host.json);
  pkgs = import (builtins.fetchTree hostLock.nixpkgs).outPath {};
  ltoPlugin = "${pkgs.stdenv.cc.cc}/libexec/gcc/${pkgs.stdenv.hostPlatform.config}/${pkgs.stdenv.cc.cc.version}/liblto_plugin.so";
  ltoAr = pkgs.writeShellScriptBin "ar" ''exec ${pkgs.binutils}/bin/ar --plugin ${ltoPlugin} "$@"'';
  ltoRanlib = pkgs.writeShellScriptBin "ranlib" ''exec ${pkgs.binutils}/bin/ranlib --plugin ${ltoPlugin} "$@"'';
in pkgs.mkShell {
  nativeBuildInputs = with pkgs; [
    ltoAr ltoRanlib
    gnumake gcc binutils gawk gnused gnugrep findutils coreutils util-linux
    bash git curl wget which gnutar gzip bzip2 xz zstd unzip rsync file
    patch diffutils perl python3 flex bison bc pkg-config texinfo help2man
    cpio gperf dtc qemu xxd
  ];
  buildInputs = with pkgs; [ ncurses zlib openssl libmd libxslt gettext elfutils libiconv ];
  hardeningDisable = [ "all" ];
  # OpenWrt bootstraps its own CMake, whose find_path cannot infer Nix's
  # compiler-wrapper include directories.
  CMAKE_INCLUDE_PATH = pkgs.lib.makeSearchPath "include" [ pkgs.glibc.dev pkgs.libiconv ];
  # Meson host builds use LTO; plain Nix binutils ar lacks GCC's plugin path.
}
