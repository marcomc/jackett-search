# putio CLI su Linux ARM64

## Esito

`putio-cli` è open source con licenza MIT. La release corrente verificata è
`v1.6.2`.

Il distributore ufficiale non pubblica un binario Linux ARM64/aarch64: lo
script di installazione supporta soltanto macOS Apple Silicon e Linux x86_64.

Il codice è però ricompilabile su ARM64. Il progetto è TypeScript/Node,
richiede Node `>=24.18.0`, e definisce sia `npm run build` sia
`npm run build:sea`. La build SEA rileva `process.arch` e prepara un runtime
Node ufficiale per quella architettura, quindi può produrre un eseguibile
`linux-arm64` se eseguita su un ambiente ARM64 compatibile.

## Fonti primarie

- Repository e README: <https://github.com/putdotio/putio-cli>
- Licenza MIT: <https://github.com/putdotio/putio-cli/blob/main/LICENSE>
- Script installer e piattaforme precompilate: <https://github.com/putdotio/putio-cli/blob/main/install.sh>
- `package.json`, versione, requisiti Node e script di build:
  <https://github.com/putdotio/putio-cli/blob/main/package.json>
- Ultima release verificata: <https://github.com/putdotio/putio-cli/releases/tag/v1.6.2>
- Build standalone SEA: <https://github.com/putdotio/putio-cli/blob/main/scripts/build-sea.mts>

## Raccomandazione

Su un host Linux ARM64, preferire una build riproducibile del tag `v1.6.2`,
validarla con `putio version` e completare `putio auth login` sull'host.
Non usare il tarball Linux amd64: su un sistema aarch64 termina con
`Exec format error`.
