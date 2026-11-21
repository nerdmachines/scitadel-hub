{
  # Pinned toolchain for the S-013 sizing harness (a measurement tool, not hub product code).
  # Run on ksb: ksb run <path-to-this-dir>#sizing -- run --out /job/out
  description = "scitadel-hub sizing harness (S-013)";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = { self, nixpkgs }:
    let
      pkgs = nixpkgs.legacyPackages.x86_64-linux;
      py = pkgs.python3.withPackages (p: [ p.tantivy p.tokenizers p.pyarrow p.zstandard ]);
      sizing = pkgs.writeShellApplication {
        name = "sizing";
        runtimeInputs = [ py pkgs.poppler-utils pkgs.cacert ];
        text = ''
          export SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
          export PYTHONPATH=${./.}
          exec python3 -m sizing.run "$@"
        '';
      };
    in {
      apps.x86_64-linux.sizing = { type = "app"; program = "${sizing}/bin/sizing"; };
      devShells.x86_64-linux.default = pkgs.mkShell { packages = [ py pkgs.poppler-utils ]; };
    };
}
