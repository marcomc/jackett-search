# Bitport.io setup

## App registration and authorization

Until Bitport confirms whether a client secret may be shared by a distributed
desktop application, assume each user registers a separate application from
their own Bitport account. Use the public Jackett Search details in Bitport's
registration form:

| Bitport field | Value |
| --- | --- |
| Application Name | `Jackett Search` |
| Application Redirect URL | `https://marcomc.github.io/jackett-search/` |
| Application Logo URL | `https://marcomc.github.io/jackett-search/assets/jackett-search-logo.png` |
| Application Page URL | `https://marcomc.github.io/jackett-search/` |

The current `--bitport-auth` command uses Bitport's device-code flow; the
required redirect URL is not used as an OAuth callback. The browser
`authorization_code` flow is not implemented.

The config template has empty `client_id` and `client_secret` fields. Fill them
manually or leave them blank for `--bitport-auth` to collect them. The command
opens the registration page, shows the values above, waits for registration,
then reads the Application ID visibly and hides the Application Secret. It
saves both in the active config file. Bitport's Application ID maps to
`client_id`:

```toml
[bitport]
client_id = ""
client_secret = ""
```

If both values are already present, `--bitport-auth` skips registration
prompts. Keep these credentials private. The command sets the active config
file mode to `0600` before reading credentials and after saving them or the
account token.

Authorize the Bitport account and save its access token:

```sh
jackett-search --bitport-auth
```

The command prints the <https://bitport.io/get-access> link and tries to open it
in the default browser. Sign in, paste the displayed `USER_CODE` into the
terminal, and the command exchanges it through Bitport's device-token endpoint.
It saves the returned token without displaying it. The API page does not
specify refresh-token behavior or token lifetime.

Each account uses its own registered app credentials and receives its own
access token. Bitport also documents a browser redirect (`authorization_code`)
flow, but this release uses only the device flow (`/get-access`, then
`grant_type=code`).
